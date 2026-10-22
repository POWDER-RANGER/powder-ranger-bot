"""Filters for the player's own input.

OneEuroFilter (Casiez, Roussel, Vogel, CHI 2012): strong smoothing when the
signal moves slowly (removes tremor and jitter), little lag when it moves fast
(keeps deliberate motion responsive). Used for the Steady assist level and
for webcam gaze.
"""

from __future__ import annotations

import math


class _LowPass:
    def __init__(self) -> None:
        self.y: float | None = None

    def __call__(self, x: float, alpha: float) -> float:
        self.y = x if self.y is None else alpha * x + (1 - alpha) * self.y
        return self.y


def _alpha(cutoff_hz: float, dt: float) -> float:
    tau = 1.0 / (2 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    def __init__(self, min_cutoff_hz: float = 1.0, beta: float = 0.02, d_cutoff_hz: float = 1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff_hz, beta, d_cutoff_hz
        self._x, self._dx = _LowPass(), _LowPass()
        self._last_x: float | None = None
        self._last_t: float | None = None

    def __call__(self, x: float, t: float) -> float:
        if self._last_t is None or t <= self._last_t:
            self._last_t, self._last_x = t, x
            return self._x(x, 1.0)
        dt = t - self._last_t
        dx = (x - self._last_x) / dt
        edx = self._dx(dx, _alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(edx)
        self._last_t, self._last_x = t, x
        return self._x(x, _alpha(cutoff, dt))
