"""Motor model: turns approved intents into human-like controller motion.

Companion output (reflex/planner) gets:
  - a reaction delay sampled from a log-normal distribution
  - minimum-jerk stick and trigger travel, duration from a Fitts-style law
  - small physiological tremor (8-12 Hz) and slow drift while a stick is held
  - button hold minimums, release gaps and a press-rate cap

Player output passes straight through (no added delay, no added tremor); the
player's own tremor is handled separately by filters.OneEuroFilter.

Every parameter lives in MotorProfile and can be fitted from a player's own
recorded input later (calibration recorder, Stage 2).
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

from ..intent import BUTTONS, GamepadFrame, Source

_AXES = ("lx", "ly", "rx", "ry", "lt", "rt")


@dataclass
class MotorProfile:
    reaction_median_ms: float = 200.0
    reaction_sigma: float = 0.25          # log-normal shape
    reaction_min_ms: float = 120.0
    reaction_max_ms: float = 400.0
    episode_gap_ms: float = 500.0         # idle time after which the next command is a new "onset" (gets a reaction delay)
    move_a_ms: float = 40.0               # Fitts: T = a + b * log2(1 + distance / width)
    move_b_ms: float = 70.0
    move_width: float = 0.15
    tremor_amp: float = 0.012             # stick units
    tremor_hz_min: float = 8.0
    tremor_hz_max: float = 12.0
    drift_sigma: float = 0.01
    drift_tau_s: float = 1.5
    hold_threshold: float = 0.05          # stick counts as "held" above this magnitude
    button_min_hold_ms: float = 60.0
    button_min_gap_ms: float = 50.0
    max_presses_per_sec: float = 8.0
    humanize: bool = True                 # development mode may switch this off for benchmarking

    @staticmethod
    def from_dict(d: dict | None) -> "MotorProfile":
        p = MotorProfile()
        for k, v in (d or {}).items():
            if not hasattr(p, k):
                raise ValueError(f"unknown motor profile field: {k}")
            setattr(p, k, bool(v) if k == "humanize" else float(v))
        return p


_CLEAR = GamepadFrame.neutral()           # sentinel queued by clear(); does not count as played output


def min_jerk(tau: float) -> float:
    tau = 0.0 if tau < 0 else 1.0 if tau > 1 else tau
    return tau ** 3 * (10 - 15 * tau + 6 * tau * tau)


@dataclass
class _Traj:
    start: float
    end: float
    t0: float
    dur: float

    def at(self, t: float) -> float:
        if self.dur <= 0:
            return self.end
        return self.start + (self.end - self.start) * min_jerk((t - self.t0) / self.dur)


class MotorModel:
    def __init__(self, profile: MotorProfile | None = None, seed: int | None = None):
        self.p = profile or MotorProfile()
        self.rng = random.Random(seed)
        self._queue: deque[tuple[float, GamepadFrame, bool]] = deque()   # (due_time, frame, humanize)
        self._target = GamepadFrame.neutral()
        self._humanize = False
        self._traj: dict[str, _Traj] = {a: _Traj(0.0, 0.0, 0.0, 0.0) for a in _AXES}
        self._pos: dict[str, float] = {a: 0.0 for a in _AXES}
        self._pressed: dict[str, float] = {}          # button -> press time
        self._released_at: dict[str, float] = {}
        self._press_times: deque[float] = deque()
        self._tremor_phase = {a: self.rng.uniform(0, 2 * math.pi) for a in ("lx", "ly", "rx", "ry")}
        self._tremor_hz = {a: self.rng.uniform(self.p.tremor_hz_min, self.p.tremor_hz_max)
                           for a in ("lx", "ly", "rx", "ry")}
        self._drift = {a: 0.0 for a in ("lx", "ly", "rx", "ry")}
        self._last_t: float | None = None
        self._last_played: float | None = None        # when a scheduled frame last reached the output
        self._onset_due = 0.0                         # earliest time the current episode may produce output

    # ------------------------------------------------------------------
    def sample_reaction_s(self) -> float:
        mu = math.log(self.p.reaction_median_ms)
        ms = self.rng.lognormvariate(mu, self.p.reaction_sigma)
        return min(max(ms, self.p.reaction_min_ms), self.p.reaction_max_ms) / 1000.0

    def movement_time_s(self, distance: float) -> float:
        if distance <= 1e-6:
            return 0.0
        return (self.p.move_a_ms + self.p.move_b_ms * math.log2(1 + distance / self.p.move_width)) / 1000.0

    def pending(self) -> bool:
        """True while scheduled frames have yet to be played."""
        return bool(self._queue)

    @property
    def last_played(self) -> float | None:
        """Time the most recent scheduled frame was played, or None if nothing is in flight."""
        return self._last_played

    def schedule(self, frames: tuple[GamepadFrame, ...], frame_dt_ms: float,
                 source: Source, now: float) -> float:
        """Merge a new chunk into the output stream. Returns the start time.

        Companion output gets one reaction delay per *episode* (the first command after
        an idle period), not one per packet: a continuous stream of chunks would otherwise
        keep erasing itself. Inside an episode a new chunk starts immediately and supersedes
        whatever is still queued from older chunks. Player output replaces everything at once.
        """
        humanize = source is not Source.PLAYER and self.p.humanize
        if not frames:
            return now
        if not humanize:
            self._queue.clear()
            start = now
        else:
            idle = (self._last_played is None
                    or (now - self._last_played) * 1000.0 > self.p.episode_gap_ms)
            if idle and not self._queue:
                self._onset_due = now + self.sample_reaction_s()
            start = max(now, self._onset_due)
            kept = [q for q in self._queue if q[0] < start]       # older frames that are already due
            self._queue.clear()
            self._queue.extend(kept)
        for i, f in enumerate(frames):
            self._queue.append((start + i * frame_dt_ms / 1000.0, f, humanize))
        return start

    def clear(self) -> None:
        """Drop pending output and head back to neutral (smoothly)."""
        self._queue.clear()
        self._queue.append((0.0, _CLEAR, True))
        self._last_played = None

    def hard_neutral(self) -> GamepadFrame:
        """Immediate neutral, no smoothing. Used by the kill switch."""
        self._queue.clear()
        self._last_played = None
        self._target = GamepadFrame.neutral()
        for a in _AXES:
            self._pos[a] = 0.0
            self._traj[a] = _Traj(0.0, 0.0, 0.0, 0.0)
        self._pressed.clear()
        for k in self._drift:
            self._drift[k] = 0.0
        return GamepadFrame.neutral()

    # ------------------------------------------------------------------
    def _retarget(self, f: GamepadFrame, humanize: bool, now: float) -> None:
        self._target, self._humanize = f, humanize
        for a in _AXES:
            goal = getattr(f, a)
            cur = self._traj[a].at(now)
            if abs(goal - self._traj[a].end) < 1e-9:
                continue
            dur = self.movement_time_s(abs(goal - cur)) if humanize else 0.0
            self._traj[a] = _Traj(cur, goal, now, dur)

    def _buttons(self, want: frozenset[str], now: float) -> frozenset[str]:
        p = self.p
        out = set()
        while self._press_times and now - self._press_times[0] > 1.0:
            self._press_times.popleft()
        for b in BUTTONS:
            down_since = self._pressed.get(b)
            if down_since is not None:
                held_ms = (now - down_since) * 1000.0
                if b in want or (self._humanize and held_ms < p.button_min_hold_ms):
                    out.add(b)
                else:
                    del self._pressed[b]
                    self._released_at[b] = now
            elif b in want:
                if self._humanize:
                    gap_ms = (now - self._released_at.get(b, -1e9)) * 1000.0
                    if gap_ms < p.button_min_gap_ms or len(self._press_times) >= p.max_presses_per_sec:
                        continue
                self._pressed[b] = now
                self._press_times.append(now)
                out.add(b)
        return frozenset(out)

    def step(self, now: float) -> GamepadFrame:
        dt = 0.0 if self._last_t is None else max(0.0, now - self._last_t)
        self._last_t = now
        while self._queue and self._queue[0][0] <= now:
            _, f, hum = self._queue.popleft()
            self._retarget(f, hum, now)
            if f is not _CLEAR:
                self._last_played = now

        vals = {a: self._traj[a].at(now) for a in _AXES}

        if self._humanize and dt > 0:
            for stick in (("lx", "ly"), ("rx", "ry")):
                held = math.hypot(vals[stick[0]], vals[stick[1]]) > self.p.hold_threshold
                for a in stick:
                    tau = self.p.drift_tau_s
                    self._drift[a] += (-self._drift[a] / tau) * dt + \
                        self.p.drift_sigma * math.sqrt(2.0 / tau) * math.sqrt(dt) * self.rng.gauss(0, 1)
                    if held:
                        vals[a] += self.p.tremor_amp * math.sin(
                            2 * math.pi * self._tremor_hz[a] * now + self._tremor_phase[a]) + self._drift[a]

        buttons = self._buttons(self._target.buttons, now)
        return GamepadFrame(vals["lx"], vals["ly"], vals["rx"], vals["ry"], vals["lt"], vals["rt"], buttons)
