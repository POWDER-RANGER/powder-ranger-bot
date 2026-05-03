# ============================================================
# capture/capture.py — mss-based screen capture
# ============================================================

from __future__ import annotations

import numpy as np
import mss


class ScreenCapture:
    def __init__(self, region: dict, monitor_idx: int = 1):
        self.region      = region
        self.monitor_idx = monitor_idx
        self._sct        = mss.mss()

    def grab(self) -> np.ndarray | None:
        try:
            screenshot = self._sct.grab(self.region)
            frame      = np.array(screenshot)
            return frame[:, :, :3]   # drop alpha → BGR
        except Exception:
            return None

    def close(self) -> None:
        self._sct.close()
