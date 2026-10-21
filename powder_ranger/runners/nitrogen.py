"""Reflex runner: NitroGen proposes, the Governor decides.

This process never touches the controller. It captures the game window,
asks the NitroGen inference server for an action chunk, converts it to
GamepadFrames, and sends one IntentPacket per chunk to the Governor.

Unlike NitroGen's own play.py, the game is NOT paused during inference (no
speed-hack DLL is injected). The game runs in real time, as for a human.

NitroGen's server speaks pickle over ZMQ and binds all interfaces by default.
Pickle from an untrusted peer can execute code, so: run the server on this
machine only, and block port 5555 inbound (scripts/lockdown_offline.ps1).
"""

from __future__ import annotations

import csv
import pickle
import time
from pathlib import Path

import numpy as np

from ..governor.client import GovernorClient
from ..intent import GamepadFrame

# Order of NitroGen's button vector (nitrogen/shared.py, BUTTON_ACTION_TOKENS).
NITROGEN_TOKENS = (
    "BACK", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "DPAD_UP", "EAST", "GUIDE",
    "LEFT_SHOULDER", "LEFT_THUMB", "LEFT_TRIGGER", "NORTH", "RIGHT_BOTTOM", "RIGHT_LEFT",
    "RIGHT_RIGHT", "RIGHT_SHOULDER", "RIGHT_THUMB", "RIGHT_TRIGGER", "RIGHT_UP", "SOUTH",
    "START", "WEST",
)
_IGNORED = {"RIGHT_BOTTOM", "RIGHT_LEFT", "RIGHT_RIGHT", "RIGHT_UP"}   # not used by NitroGen's own player
BUTTON_THRESHOLD = 0.5


def prediction_to_frames(pred: dict, threshold: float = BUTTON_THRESHOLD) -> list[GamepadFrame]:
    """Convert a NitroGen prediction to GamepadFrames.

    NitroGen joysticks use +y = down (its play.py negates y before XInput);
    GamepadFrame uses +y = up, so y is negated here.
    """
    j_left = np.asarray(pred["j_left"], dtype=float).reshape(-1, 2)
    j_right = np.asarray(pred["j_right"], dtype=float).reshape(-1, 2)
    buttons = np.asarray(pred["buttons"], dtype=float)
    if buttons.ndim == 1:
        buttons = buttons.reshape(1, -1)
    n = len(buttons)
    if not (len(j_left) == len(j_right) == n):
        raise ValueError("prediction length mismatch")
    if buttons.shape[1] != len(NITROGEN_TOKENS):
        raise ValueError(f"expected {len(NITROGEN_TOKENS)} button values, got {buttons.shape[1]}")
    frames = []
    for i in range(n):
        vals = dict(zip(NITROGEN_TOKENS, buttons[i]))
        pressed = frozenset(name for name, v in vals.items()
                            if name not in _IGNORED and "TRIGGER" not in name and v > threshold)
        frames.append(GamepadFrame(
            lx=j_left[i][0], ly=-j_left[i][1],
            rx=j_right[i][0], ry=-j_right[i][1],
            lt=vals["LEFT_TRIGGER"], rt=vals["RIGHT_TRIGGER"],
            buttons=pressed,
        ))
    return frames


class NitroGenServer:
    """Minimal client for NitroGen's scripts/serve.py (pickle over ZMQ REQ)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5555, timeout_ms: int = 30000):
        import zmq
        self._zmq = zmq
        self.addr = f"tcp://{host}:{port}"
        self.timeout_ms = timeout_ms
        self._ctx = zmq.Context.instance()
        self._connect()

    def _connect(self) -> None:
        zmq = self._zmq
        self.sock = self._ctx.socket(zmq.REQ)
        self.sock.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        self.sock.setsockopt(zmq.LINGER, 0)
        self.sock.connect(self.addr)

    def _call(self, request: dict) -> dict:
        self.sock.send(pickle.dumps(request))
        try:
            resp = pickle.loads(self.sock.recv())   # local server only; see module docstring
        except self._zmq.Again:
            self.sock.close()
            self._connect()                          # a REQ socket is stuck after a timeout
            raise TimeoutError("NitroGen server did not answer in time")
        if resp.get("status") != "ok":
            raise RuntimeError(resp.get("message", "server error"))
        return resp

    def reset(self) -> None:
        self._call({"type": "reset"})

    def info(self) -> dict:
        return self._call({"type": "info"})["info"]

    def predict(self, image) -> dict:
        return self._call({"type": "predict", "image": image})["pred"]


def run(governor: GovernorClient, process_name: str, delegation_id: str, *,
        port: int = 5555, env_fps: int = 60, capture_fps: int = 30,
        metrics_path: str | Path = "logs/reflex_metrics.csv", max_steps: int | None = None,
        capture=None, server=None) -> int:
    """Returns the number of chunks sent. `capture` (anything with grab() and
    close()) and `server` can be injected for headless tests."""
    from PIL import Image

    server = server or NitroGenServer(port=port)
    server.reset()
    info = server.info()
    ratio = int(info.get("action_downsample_ratio", 1))
    frame_dt_ms = 1000.0 / env_fps * ratio
    print(f"NitroGen ready: checkpoint={info.get('ckpt_path')} downsample={ratio} -> {frame_dt_ms:.1f} ms per action")

    if capture is None:
        from ..capture.screen import WindowCapture
        capture = WindowCapture(process_name, target_fps=capture_fps)
    cap = capture
    metrics_path = Path(metrics_path)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not metrics_path.exists()
    step = 0
    with metrics_path.open("a", newline="") as mf:
        w = csv.writer(mf)
        if new_file:
            w.writerow(["t_wall", "step", "capture_ms", "inference_ms", "actions", "chunk_ms"])
        try:
            while max_steps is None or step < max_steps:
                t0 = time.perf_counter()
                frame = cap.grab()
                if frame is None:
                    time.sleep(0.005)
                    continue
                img = Image.fromarray(frame).resize((256, 256), Image.Resampling.BOX)
                t1 = time.perf_counter()
                pred = server.predict(img)
                t2 = time.perf_counter()
                frames = prediction_to_frames(pred)
                # Each NitroGen action is held for `ratio` game frames.
                governor.send_frames(frames, frame_dt_ms=frame_dt_ms, ttl_ms=400,
                                     delegation_id=delegation_id, note="nitrogen chunk")
                w.writerow([f"{time.time():.3f}", step, f"{(t1 - t0) * 1000:.1f}",
                            f"{(t2 - t1) * 1000:.1f}", len(frames), f"{len(frames) * frame_dt_ms:.0f}"])
                mf.flush()
                step += 1
        finally:
            cap.close()
    return step
