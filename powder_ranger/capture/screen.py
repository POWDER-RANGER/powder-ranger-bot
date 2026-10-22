"""Screen capture of the target game's window (Windows).

Perception is screen-only by design: the companion sees exactly what a player
sees, nothing from game memory.
"""

from __future__ import annotations

import ctypes
import sys

IS_WINDOWS = sys.platform == "win32"


_DPI_SET = False


def make_dpi_aware() -> None:
    """Without this, Windows reports window rectangles in scaled (logical) pixels
    on a 125%/150% display while dxcam captures physical pixels: the crop would
    miss part of the game. Must run before the first rectangle query."""
    global _DPI_SET
    if _DPI_SET or not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    _DPI_SET = True


def find_window_rect(process_name: str) -> tuple[int, int, int, int]:
    """Client-area rectangle (left, top, right, bottom), in physical pixels, of the
    largest visible window owned by process_name."""
    if not IS_WINDOWS:
        raise RuntimeError("window capture is Windows-only")
    make_dpi_aware()
    import ctypes.wintypes as wt
    import psutil

    pids = {p.pid for p in psutil.process_iter(["name"])
            if (p.info.get("name") or "").lower() == process_name.lower()}
    if not pids:
        raise RuntimeError(f"process not running: {process_name}")

    user32 = ctypes.windll.user32
    found: list[tuple[int, tuple[int, int, int, int]]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def enum_cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            rc = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rc))
            pt = wt.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            w, h = rc.right - rc.left, rc.bottom - rc.top
            if w > 0 and h > 0:
                found.append((w * h, (pt.x, pt.y, pt.x + w, pt.y + h)))
        return True

    user32.EnumWindows(enum_cb, 0)
    if not found:
        raise RuntimeError(f"no visible window for {process_name}")
    return max(found)[1]


class WindowCapture:
    """dxcam-based capture of a window region. grab() returns an RGB numpy
    array, or None when no new frame is ready."""

    def __init__(self, process_name: str, target_fps: int = 30):
        import dxcam
        self.process_name = process_name
        self.region = find_window_rect(process_name)
        self.camera = dxcam.create(output_color="RGB")
        self.camera.start(region=self.region, target_fps=target_fps, video_mode=True)

    def grab(self):
        return self.camera.get_latest_frame()

    def close(self) -> None:
        try:
            self.camera.stop()
        except Exception:
            pass
