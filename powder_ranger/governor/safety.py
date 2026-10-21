"""Kill switch and focus check.

Kill switch: latched. Once tripped, output is neutral and every packet is
denied until an explicit resume. Trip sources: global hotkey (Windows),
a STOP file on disk, or a call to trip().

Focus: companion output is only allowed while the target game window is in
front, so a stray packet can never type into another program.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from pathlib import Path
from typing import Callable

IS_WINDOWS = sys.platform == "win32"

# Virtual-key codes and modifiers (Win32)
VK_PAUSE = 0x13
VK_R = 0x52
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
WM_HOTKEY = 0x0312


class KillSwitch:
    def __init__(self, stop_file: str | Path | None = None):
        self._tripped = threading.Event()
        self._resume_requested = threading.Event()
        self.reason = ""
        self.stop_file = Path(stop_file) if stop_file else None
        self._listeners: list[Callable[[str], None]] = []

    @property
    def tripped(self) -> bool:
        return self._tripped.is_set()

    def on_trip(self, fn: Callable[[str], None]) -> None:
        self._listeners.append(fn)

    def trip(self, reason: str) -> None:
        if not self._tripped.is_set():
            self.reason = reason
            self._tripped.set()
            for fn in self._listeners:
                fn(reason)

    def request_resume(self) -> None:
        self._resume_requested.set()

    def take_resume_request(self) -> bool:
        """The Governor calls this; resume is applied (and logged) by the Governor."""
        if self._resume_requested.is_set():
            self._resume_requested.clear()
            return True
        return False

    def clear(self) -> None:
        self._tripped.clear()
        self.reason = ""

    def poll_stop_file(self) -> None:
        if self.stop_file is not None and self.stop_file.exists():
            self.trip(f"stop file present: {self.stop_file}")

    def start_hotkeys(self, kill_vk: int = VK_PAUSE, kill_mods: int = 0,
                      resume_vk: int = VK_R, resume_mods: int = MOD_CONTROL | MOD_ALT) -> bool:
        """Register global hotkeys on a dedicated thread. Returns False when
        unavailable (non-Windows, or the key is already taken)."""
        if not IS_WINDOWS:
            return False
        ready = threading.Event()
        ok = {"value": False}

        def run() -> None:
            user32 = ctypes.windll.user32
            k = user32.RegisterHotKey(None, 1, kill_mods | MOD_NOREPEAT, kill_vk)
            r = user32.RegisterHotKey(None, 2, resume_mods | MOD_NOREPEAT, resume_vk)
            ok["value"] = bool(k)
            ready.set()
            if not k:
                return
            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY:
                    if msg.wParam == 1:
                        self.trip("kill hotkey")
                    elif msg.wParam == 2 and r:
                        self.request_resume()

        import ctypes.wintypes  # noqa: F401  (Windows only)
        threading.Thread(target=run, name="killswitch-hotkeys", daemon=True).start()
        ready.wait(2.0)
        return ok["value"]


class FocusChecker:
    """True when the foreground window belongs to the target process."""

    def __init__(self, process_name: str | None, assume_focused_off_windows: bool = False):
        self.process_name = (process_name or "").lower()
        self.assume = assume_focused_off_windows

    def __call__(self) -> bool:
        if not self.process_name:
            return self.assume
        if not IS_WINDOWS:
            return self.assume
        try:
            import psutil
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return psutil.Process(pid.value).name().lower() == self.process_name
        except Exception:
            return False
