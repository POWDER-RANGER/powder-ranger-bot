"""Calibration: record a player's own controller and fit a MotorProfile.

Recording: XInput at a fixed rate to JSONL ({"t": seconds, "f": GamepadFrame dict}).

Fitted from the recording (what a free-play recording can actually show):
  button_min_hold_ms    5th percentile of press durations
  button_min_gap_ms     5th percentile of release->press gaps (same button)
  max_presses_per_sec   peak presses inside any 1 s window
  move_a_ms, move_b_ms  Fitts-law fit of stick movement time vs distance
                        (slope is reliable; the intercept reads low because the
                        slow start and end of a movement fall under the threshold)
  tremor_amp            RMS deviation while a stick is held steady
  tremor_hz_min/max     dominant frequency band of that deviation

NOT fitted: reaction time. It needs a stimulus with a known onset; a free-play
recording has none. Use a reaction test (planned) or keep the default.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from ..intent import BUTTONS, GamepadFrame
from .model import MotorProfile


def record(source, path: str | Path, seconds: float, hz: float = 120.0) -> int:
    """source: anything with read() -> GamepadFrame | None (e.g. inputs.player.XInputSource)."""
    n = 0
    period = 1.0 / hz
    t0 = time.perf_counter()
    with Path(path).open("w", encoding="utf-8") as fh:
        while (now := time.perf_counter()) - t0 < seconds:
            f = source.read()
            if f is not None:
                fh.write(json.dumps({"t": round(now - t0, 5), "f": f.to_dict()}) + "\n")
                n += 1
            time.sleep(max(0.0, period - (time.perf_counter() - now)))
    return n


def load(path: str | Path) -> tuple[np.ndarray, list[GamepadFrame]]:
    ts, frames = [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            ts.append(d["t"])
            frames.append(GamepadFrame.from_dict(d["f"]))
    return np.asarray(ts), frames


def _press_stats(ts: np.ndarray, frames: list[GamepadFrame]) -> dict:
    holds, gaps, press_times = [], [], []
    for b in BUTTONS:
        down_at, up_at = None, None
        for t, f in zip(ts, frames):
            pressed = b in f.buttons
            if pressed and down_at is None:
                down_at = t
                press_times.append(t)
                if up_at is not None:
                    gaps.append((t - up_at) * 1000)
            elif not pressed and down_at is not None:
                holds.append((t - down_at) * 1000)
                down_at, up_at = None, t
    press_times.sort()
    peak = 0
    j = 0
    for i, t in enumerate(press_times):
        while press_times[j] < t - 1.0:
            j += 1
        peak = max(peak, i - j + 1)
    pct = lambda xs, q: float(np.percentile(xs, q)) if xs else None
    return {"holds": holds, "gaps": gaps, "min_hold": pct(holds, 5), "min_gap": pct(gaps, 5), "peak_rate": peak}


def _segments(ts: np.ndarray, x: np.ndarray, still: float = 0.02, min_dist: float = 0.2):
    """Movements between two still periods: (distance, duration_s)."""
    v = np.abs(np.gradient(x, ts))
    moving = v > still / max(1e-6, float(np.median(np.diff(ts))))
    out, start = [], None
    for i in range(1, len(x)):
        if moving[i] and not moving[i - 1]:
            start = i - 1
        elif not moving[i] and moving[i - 1] and start is not None:
            dist = abs(x[i] - x[start])
            if dist >= min_dist:
                out.append((dist, ts[i] - ts[start]))
            start = None
    return out


def _fit_fitts(segs, width: float) -> tuple[float, float] | None:
    if len(segs) < 5:
        return None
    ids = np.array([math.log2(1 + d / width) for d, _ in segs])
    mts = np.array([dt * 1000 for _, dt in segs])
    b, a = np.polyfit(ids, mts, 1)
    if b <= 0:
        return None
    return float(max(a, 0.0)), float(b)


def _tremor(ts: np.ndarray, x: np.ndarray, hold_threshold: float, min_len_s: float = 1.0):
    """Tremor from stretches where the stick is held away from centre and nearly still."""
    amps, peaks = [], []
    dt = float(np.median(np.diff(ts))) if len(ts) > 1 else 1 / 120
    held = np.abs(x) > max(hold_threshold, 0.2)
    i = 0
    while i < len(x):
        if held[i]:
            j = i
            while j < len(x) and held[j]:
                j += 1
            seg = x[i:j]
            if (j - i) * dt >= min_len_s:
                k = max(3, int(0.25 / dt))                     # remove slow drift: 0.25 s moving average
                trend = np.convolve(seg, np.ones(k) / k, mode="same")
                resid = (seg - trend)[k:-k]
                if len(resid) > 16:
                    amps.append(float(np.sqrt(np.mean(resid ** 2)) * math.sqrt(2)))
                    spec = np.abs(np.fft.rfft(resid * np.hanning(len(resid))))
                    freqs = np.fft.rfftfreq(len(resid), dt)
                    band = (freqs >= 2) & (freqs <= 20)
                    if band.any():
                        peaks.append(float(freqs[band][np.argmax(spec[band])]))
            i = j
        else:
            i += 1
    return amps, peaks


def fit_profile(path: str | Path, base: MotorProfile | None = None) -> tuple[MotorProfile, dict]:
    """Returns (profile, report). Fields with too little evidence keep the base value."""
    base = base or MotorProfile()
    ts, frames = load(path)
    p = MotorProfile(**asdict(base))
    report: dict = {"samples": len(frames), "duration_s": float(ts[-1] - ts[0]) if len(ts) > 1 else 0.0,
                    "fitted": {}, "kept_default": [], "not_fitted": ["reaction_* (needs a stimulus test)"]}

    ps = _press_stats(ts, frames)
    if ps["min_hold"] is not None and len(ps["holds"]) >= 10:
        p.button_min_hold_ms = round(ps["min_hold"], 1)
        report["fitted"]["button_min_hold_ms"] = f"{p.button_min_hold_ms} (from {len(ps['holds'])} presses)"
    else:
        report["kept_default"].append("button_min_hold_ms")
    if ps["min_gap"] is not None and len(ps["gaps"]) >= 10:
        p.button_min_gap_ms = round(ps["min_gap"], 1)
        report["fitted"]["button_min_gap_ms"] = f"{p.button_min_gap_ms} (from {len(ps['gaps'])} gaps)"
    else:
        report["kept_default"].append("button_min_gap_ms")
    if ps["peak_rate"] >= 2:
        p.max_presses_per_sec = float(ps["peak_rate"])
        report["fitted"]["max_presses_per_sec"] = p.max_presses_per_sec
    else:
        report["kept_default"].append("max_presses_per_sec")

    segs = []
    for axis in ("lx", "ly", "rx", "ry"):
        segs += _segments(ts, np.array([getattr(f, axis) for f in frames]))
    fitts = _fit_fitts(segs, base.move_width)
    if fitts:
        p.move_a_ms, p.move_b_ms = round(fitts[0], 1), round(fitts[1], 1)
        report["fitted"]["move_a_ms/move_b_ms"] = f"{p.move_a_ms}/{p.move_b_ms} (from {len(segs)} movements)"
    else:
        report["kept_default"].append("move_a_ms/move_b_ms")

    amps, peaks = [], []
    for axis in ("lx", "ly", "rx", "ry"):
        a, pk = _tremor(ts, np.array([getattr(f, axis) for f in frames]), base.hold_threshold)
        amps += a
        peaks += pk
    if amps:
        p.tremor_amp = round(statistics.median(amps), 4)
        report["fitted"]["tremor_amp"] = p.tremor_amp
    else:
        report["kept_default"].append("tremor_amp")
    if peaks:
        lo, hi = float(np.percentile(peaks, 10)), float(np.percentile(peaks, 90))
        p.tremor_hz_min, p.tremor_hz_max = round(lo, 1), round(max(hi, lo + 0.5), 1)
        report["fitted"]["tremor_hz"] = f"{p.tremor_hz_min}-{p.tremor_hz_max}"
    else:
        report["kept_default"].append("tremor_hz_min/max")
    return p, report


def profile_yaml(p: MotorProfile, name: str) -> str:
    lines = [f"# Fitted motor profile for {name}. Generated by `powder_ranger calibrate`.",
             f"name: {name}", "motor:"]
    for k, v in asdict(p).items():
        lines.append(f"  {k}: {str(v).lower() if isinstance(v, bool) else v}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Reaction test: the one parameter free play cannot show
# ---------------------------------------------------------------------------

def fit_reaction(times_ms: list[float], base: MotorProfile | None = None,
                 too_fast_ms: float = 100.0) -> tuple[MotorProfile, dict]:
    """Log-normal fit of reaction times. Presses under too_fast_ms are anticipations
    (guesses before the cue), not reactions, and are dropped."""
    base = base or MotorProfile()
    p = MotorProfile(**asdict(base))
    valid = [t for t in times_ms if t >= too_fast_ms]
    report = {"trials": len(times_ms), "valid": len(valid), "anticipations": len(times_ms) - len(valid)}
    if len(valid) < 8:
        report["kept_default"] = "reaction_* (fewer than 8 valid trials)"
        return p, report
    logs = np.log(valid)
    p.reaction_median_ms = round(float(np.exp(np.median(logs))), 1)
    p.reaction_sigma = round(float(np.std(logs, ddof=1)), 3)
    p.reaction_min_ms = round(float(np.percentile(valid, 2)), 1)
    p.reaction_max_ms = round(float(np.percentile(valid, 98)), 1)
    report["fitted"] = {k: getattr(p, k) for k in
                        ("reaction_median_ms", "reaction_sigma", "reaction_min_ms", "reaction_max_ms")}
    return p, report


def run_reaction_test(source, trials: int = 20, min_wait_s: float = 1.5, max_wait_s: float = 4.0,
                      timeout_s: float = 2.0) -> list[float]:
    """Full-screen cue: wait (random), screen turns green, player presses any button.
    Uses tkinter (bundled with Python on Windows). Returns reaction times in ms;
    a press before the cue is recorded as 0 (an anticipation)."""
    import random
    import tkinter as tk

    rng = random.Random()
    times: list[float] = []
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.configure(bg="black")
    label = tk.Label(root, text="", fg="white", bg="black", font=("Segoe UI", 36))
    label.pack(expand=True)

    def pressed() -> bool:
        f = source.read()
        return f is not None and bool(f.buttons)

    def show(text: str, bg: str) -> None:
        root.configure(bg=bg)
        label.configure(text=text, bg=bg)
        root.update()

    try:
        show("Reaction test: press any button when the screen turns GREEN.\nStarting...", "black")
        time.sleep(2.5)
        for i in range(trials):
            show(f"Wait...  ({i + 1}/{trials})", "black")
            while pressed():                       # let go first
                root.update(); time.sleep(0.005)
            deadline = time.perf_counter() + rng.uniform(min_wait_s, max_wait_s)
            early = False
            while time.perf_counter() < deadline:
                if pressed():
                    early = True
                    break
                root.update(); time.sleep(0.002)
            if early:
                times.append(0.0)
                show("Too soon.", "#552200"); time.sleep(0.8)
                continue
            show("", "#00aa44")
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < timeout_s and not pressed():
                time.sleep(0.001)
            rt = (time.perf_counter() - t0) * 1000
            if rt < timeout_s * 1000:
                times.append(rt)
                show(f"{rt:.0f} ms", "black")
            else:
                show("Missed - that's fine.", "black")
            time.sleep(0.7)
    finally:
        root.destroy()
    return times
