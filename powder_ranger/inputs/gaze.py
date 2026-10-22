"""Webcam gaze: look to steer, look-and-hold to select, long blink to confirm.

Pipeline (all local):
  webcam -> MediaPipe Face Landmarker (iris landmarks) -> eye features
         -> per-player calibration (9 points, quadratic fit) -> screen point
         -> One Euro smoothing -> GazeStick (steer) / DwellSelector (choose)
  eye aspect ratio -> BlinkDetector (deliberate long blinks only)

Fixes from the original prototype: real iris features (not an eye bounding
box), a fitted calibration (not hardcoded points), and a blink that must be
held on purpose (a normal blink or a missed detection never confirms).

Everything except the webcam loop is pure math and unit-tested.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..intent import GamepadFrame
from ..motor.filters import OneEuroFilter

# MediaPipe face mesh indices (with refined iris landmarks)
L_IRIS, R_IRIS = 468, 473
L_OUTER, L_INNER, L_TOP, L_BOTTOM = 33, 133, 159, 145
R_INNER, R_OUTER, R_TOP, R_BOTTOM = 362, 263, 386, 374
L_EAR_PTS = (33, 160, 158, 133, 153, 144)
R_EAR_PTS = (362, 385, 387, 263, 373, 380)


def eye_features(lm: np.ndarray) -> np.ndarray:
    """lm: (N, 2+) normalized landmarks. Returns [x, y]: iris position inside the
    eye opening, averaged over both eyes; ~0.5 = looking straight."""
    def one(iris, a, b, top, bottom):
        ex = (lm[iris, 0] - lm[a, 0]) / max(1e-6, lm[b, 0] - lm[a, 0])
        ey = (lm[iris, 1] - lm[top, 1]) / max(1e-6, lm[bottom, 1] - lm[top, 1])
        return ex, ey
    lx, ly = one(L_IRIS, L_OUTER, L_INNER, L_TOP, L_BOTTOM)
    rx, ry = one(R_IRIS, R_INNER, R_OUTER, R_TOP, R_BOTTOM)
    return np.array([(lx + rx) / 2, (ly + ry) / 2])


def eye_aspect_ratio(lm: np.ndarray) -> float:
    """Mean EAR of both eyes (Soukupova & Cech 2016). ~0.3 open, < 0.15 closed."""
    def ear(p):
        p1, p2, p3, p4, p5, p6 = (lm[i, :2] for i in p)
        return (np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2 * np.linalg.norm(p1 - p4) + 1e-9)
    return float((ear(L_EAR_PTS) + ear(R_EAR_PTS)) / 2)


def _poly(f: np.ndarray) -> np.ndarray:
    x, y = f[..., 0], f[..., 1]
    return np.stack([np.ones_like(x), x, y, x * y, x * x, y * y], axis=-1)


class GazeCalibration:
    """Quadratic map from eye features to screen pixels, fitted per player."""

    def __init__(self) -> None:
        self.coef: np.ndarray | None = None
        self.rms_px: float | None = None

    def fit(self, features: np.ndarray, targets: np.ndarray) -> float:
        """features (n, 2), targets (n, 2) in pixels. Needs >= 6 points; 9 recommended.
        Returns the RMS error in pixels on the calibration points."""
        if len(features) < 6:
            raise ValueError("need at least 6 calibration points")
        A = _poly(np.asarray(features, float))
        self.coef, *_ = np.linalg.lstsq(A, np.asarray(targets, float), rcond=None)
        err = A @ self.coef - targets
        self.rms_px = float(np.sqrt(np.mean(np.sum(err ** 2, axis=1))))
        return self.rms_px

    def __call__(self, feature: np.ndarray) -> np.ndarray:
        if self.coef is None:
            raise RuntimeError("calibrate first")
        return _poly(np.asarray(feature, float)) @ self.coef

    def to_dict(self) -> dict:
        return {"coef": self.coef.tolist() if self.coef is not None else None, "rms_px": self.rms_px}

    @staticmethod
    def from_dict(d: dict) -> "GazeCalibration":
        c = GazeCalibration()
        c.coef = np.asarray(d["coef"]) if d.get("coef") is not None else None
        c.rms_px = d.get("rms_px")
        return c


def calibration_targets(width: int, height: int, margin: float = 0.1) -> np.ndarray:
    """The 9 on-screen points the player looks at, row by row."""
    xs = [width * margin, width / 2, width * (1 - margin)]
    ys = [height * margin, height / 2, height * (1 - margin)]
    return np.array([(x, y) for y in ys for x in xs])


class BlinkDetector:
    """Fires once per deliberate long blink: eyes closed for at least hold_ms.
    Normal blinks (100-300 ms) and single-frame dropouts never fire."""

    def __init__(self, closed_ear: float = 0.17, hold_ms: float = 450, max_ms: float = 2500):
        self.closed_ear, self.hold_ms, self.max_ms = closed_ear, hold_ms, max_ms
        self._closed_since: float | None = None
        self._fired = False

    def update(self, ear: float | None, t: float) -> bool:
        if ear is None:                       # no face: treat as open, reset
            self._closed_since, self._fired = None, False
            return False
        if ear < self.closed_ear:
            if self._closed_since is None:
                self._closed_since = t
            held = (t - self._closed_since) * 1000
            if not self._fired and self.hold_ms <= held <= self.max_ms:
                self._fired = True
                return True
            return False
        self._closed_since, self._fired = None, False
        return False


@dataclass
class Zone:
    name: str
    x0: float
    y0: float
    x1: float
    y1: float

    def contains(self, p: np.ndarray) -> bool:
        return self.x0 <= p[0] <= self.x1 and self.y0 <= p[1] <= self.y1


class DwellSelector:
    """Selecting by looking: a zone is chosen when gaze stays inside it for dwell_ms.
    progress() drives an on-screen fill so the player sees it coming."""

    def __init__(self, zones: list[Zone], dwell_ms: float = 900):
        self.zones, self.dwell_ms = zones, dwell_ms
        self._zone: Zone | None = None
        self._since = 0.0
        self._done = False

    def update(self, p: np.ndarray | None, t: float) -> str | None:
        z = next((z for z in self.zones if p is not None and z.contains(p)), None)
        if z is not self._zone:
            self._zone, self._since, self._done = z, t, False
            return None
        if z is not None and not self._done and (t - self._since) * 1000 >= self.dwell_ms:
            self._done = True
            return z.name
        return None

    def progress(self, t: float) -> float:
        if self._zone is None or self._done:
            return 0.0
        return min(1.0, (t - self._since) * 1000 / self.dwell_ms)


class GazeStick:
    """Look where you want to go: gaze offset from the screen centre becomes the
    left stick. A centre dead zone means 'straight'; the edge zone is full lock."""

    def __init__(self, width: int, height: int, dead: float = 0.12, full: float = 0.8,
                 vertical: bool = False):
        self.w, self.h, self.dead, self.full, self.vertical = width, height, dead, full, vertical

    def __call__(self, p: np.ndarray) -> tuple[float, float]:
        nx = (p[0] - self.w / 2) / (self.w / 2)
        ny = -(p[1] - self.h / 2) / (self.h / 2)          # screen y down -> stick y up

        def shape(v: float) -> float:
            a = abs(v)
            if a <= self.dead:
                return 0.0
            return float(np.sign(v) * min(1.0, (a - self.dead) / (self.full - self.dead)))
        return shape(nx), (shape(ny) if self.vertical else 0.0)


class GazeSource:
    """InputSource for PlayerInputLoop: gaze steers the left stick; a long blink
    taps `blink_button`. features_fn returns (features, ear) or None when no face."""

    def __init__(self, features_fn: Callable[[], tuple[np.ndarray, float] | None], calibration: GazeCalibration,
                 stick: GazeStick, blink_button: str | None = "SOUTH", clock: Callable[[], float] = time.monotonic):
        self.name = "gaze"
        self.features_fn, self.cal, self.stick, self.blink_button = features_fn, calibration, stick, blink_button
        self.blink = BlinkDetector()
        self.fx, self.fy = OneEuroFilter(1.0, 0.01), OneEuroFilter(1.0, 0.01)
        self.clock = clock
        self._tap_until = 0.0
        self.last_point: np.ndarray | None = None

    def claims(self, f: GamepadFrame) -> tuple[str, ...]:
        """Gaze owns steering (and vertical aim if enabled); buttons only while blink-tapping."""
        c = ("lx", "ly") if self.stick.vertical else ("lx",)
        return c + (("buttons",) if f.buttons else ())

    def read(self) -> GamepadFrame:
        t = self.clock()
        got = self.features_fn()
        if got is None:
            self.blink.update(None, t)
            self.last_point = None
            return GamepadFrame()                 # no face: hands off
        feat, ear = got
        if self.blink.update(ear, t) and self.blink_button:
            self._tap_until = t + 0.12
        if ear < self.blink.closed_ear:           # eyes shut: hold the last steering, no new aim
            p = self.last_point
        else:
            raw = self.cal(feat)
            p = np.array([self.fx(float(raw[0]), t), self.fy(float(raw[1]), t)])
            self.last_point = p
        lx, ly = self.stick(p) if p is not None else (0.0, 0.0)
        buttons = frozenset({self.blink_button}) if t < self._tap_until and self.blink_button else frozenset()
        return GamepadFrame(lx=lx, ly=ly, buttons=buttons)


def mediapipe_features(model_path: str, camera_index: int = 0):
    """Returns a features_fn backed by the webcam and MediaPipe Face Landmarker.
    model_path: face_landmarker.task (download once in prep mode)."""
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

    cam = cv2.VideoCapture(camera_index)
    landmarker = FaceLandmarker.create_from_options(FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path), running_mode=RunningMode.VIDEO, num_faces=1))
    t0 = time.monotonic()

    def fn():
        ok, frame = cam.read()
        if not ok:
            return None
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        res = landmarker.detect_for_video(img, int((time.monotonic() - t0) * 1000))
        if not res.face_landmarks:
            return None
        lm = np.array([[p.x, p.y] for p in res.face_landmarks[0]])
        if len(lm) < 478:
            return None
        return eye_features(lm), eye_aspect_ratio(lm)
    return fn


def run_calibration(features_fn, settle_s: float = 0.7, sample_s: float = 1.0) -> tuple[GazeCalibration, dict]:
    """Full-screen 9-point calibration with tkinter. The player looks at each dot."""
    import tkinter as tk

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.configure(bg="black")
    root.update()
    w, h = root.winfo_screenwidth(), root.winfo_screenheight()
    canvas = tk.Canvas(root, width=w, height=h, bg="black", highlightthickness=0)
    canvas.pack()
    targets = calibration_targets(w, h)
    feats, used, missed = [], [], 0
    try:
        canvas.create_text(w / 2, h / 2, text="Look at each dot until it moves.", fill="white",
                           font=("Segoe UI", 32))
        root.update(); time.sleep(2.0)
        for tx, ty in targets:
            canvas.delete("all")
            canvas.create_oval(tx - 18, ty - 18, tx + 18, ty + 18, fill="#00c060", outline="")
            canvas.create_oval(tx - 4, ty - 4, tx + 4, ty + 4, fill="white", outline="")
            root.update()
            end_settle = time.monotonic() + settle_s
            while time.monotonic() < end_settle:
                features_fn(); root.update()
            samples = []
            end = time.monotonic() + sample_s
            while time.monotonic() < end:
                got = features_fn()
                if got is not None and got[1] > 0.17:
                    samples.append(got[0])
                root.update()
            if len(samples) >= 5:
                feats.append(np.median(np.array(samples), axis=0))
                used.append((tx, ty))
            else:
                missed += 1
    finally:
        root.destroy()
    cal = GazeCalibration()
    rms = cal.fit(np.array(feats), np.array(used))
    return cal, {"points_used": len(used), "points_missed": missed, "rms_px": round(rms, 1),
                 "screen": [w, h]}
