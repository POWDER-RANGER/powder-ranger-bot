"""Player input channel: the player's own controls, sent to the Governor as
PLAYER packets. Player packets always pass and pre-empt the companion.

A source is anything with read() -> GamepadFrame | None (None = device gone).
Sources here:
  XInputSource    a physical Xbox-compatible pad (Windows)
  KeyboardSource  keys or adaptive switches that type keys (Windows)
  FakeSource      scripted frames, for tests

PlayerInputLoop:
  - sends the player's state while it is non-neutral (the player is acting)
  - sources with a claims(frame) method send partial claims (shared control:
    e.g. gaze owns steering, the companion keeps throttle); others take the whole pad
  - sends one neutral frame when the player lets go, then goes quiet so the
    companion can resume after player_override_hold_ms
  - optional One Euro smoothing of sticks (the "Steady" assist level)
  - sends presence heartbeats while the player is active
"""

from __future__ import annotations

import ctypes
import sys
import time
from typing import Callable, Protocol

from ..intent import GamepadFrame
from ..motor.filters import OneEuroFilter

IS_WINDOWS = sys.platform == "win32"


class InputSource(Protocol):
    name: str

    def read(self) -> GamepadFrame | None: ...


def is_neutral(f: GamepadFrame, stick_eps: float = 0.0, trig_eps: float = 0.0) -> bool:
    return (not f.buttons and abs(f.lx) <= stick_eps and abs(f.ly) <= stick_eps
            and abs(f.rx) <= stick_eps and abs(f.ry) <= stick_eps
            and f.lt <= trig_eps and f.rt <= trig_eps)


# ---------------------------------------------------------------------------
# XInput (Windows)
# ---------------------------------------------------------------------------

XINPUT_BUTTONS = {
    0x0001: "DPAD_UP", 0x0002: "DPAD_DOWN", 0x0004: "DPAD_LEFT", 0x0008: "DPAD_RIGHT",
    0x0010: "START", 0x0020: "BACK", 0x0040: "LEFT_THUMB", 0x0080: "RIGHT_THUMB",
    0x0100: "LEFT_SHOULDER", 0x0200: "RIGHT_SHOULDER",
    0x1000: "SOUTH", 0x2000: "EAST", 0x4000: "WEST", 0x8000: "NORTH",
}
LEFT_DEADZONE, RIGHT_DEADZONE, TRIGGER_THRESHOLD = 7849, 8689, 30   # Microsoft's XInput defaults


class _XState(ctypes.Structure):
    _fields_ = [("packet", ctypes.c_uint), ("buttons", ctypes.c_ushort),
                ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                ("lx", ctypes.c_short), ("ly", ctypes.c_short),
                ("rx", ctypes.c_short), ("ry", ctypes.c_short)]


def _stick(x: int, y: int, dz: int) -> tuple[float, float]:
    mag = (x * x + y * y) ** 0.5
    if mag <= dz:
        return 0.0, 0.0
    scale = min(1.0, (mag - dz) / (32767 - dz)) / mag
    return x * scale, y * scale


def xinput_state_to_frame(buttons: int, lt: int, rt: int, lx: int, ly: int, rx: int, ry: int) -> GamepadFrame:
    """Raw XInput values -> GamepadFrame with standard dead zones. XInput +y is up."""
    flx, fly = _stick(lx, ly, LEFT_DEADZONE)
    frx, fry = _stick(rx, ry, RIGHT_DEADZONE)
    trig = lambda v: 0.0 if v <= TRIGGER_THRESHOLD else (v - TRIGGER_THRESHOLD) / (255 - TRIGGER_THRESHOLD)
    names = frozenset(n for bit, n in XINPUT_BUTTONS.items() if buttons & bit)
    return GamepadFrame(flx, fly, frx, fry, trig(lt), trig(rt), names)


def xinput_connected_slots() -> list[int]:
    if not IS_WINDOWS:
        return []
    x = ctypes.windll.xinput1_4
    s = _XState()
    return [i for i in range(4) if x.XInputGetState(i, ctypes.byref(s)) == 0]


class XInputSource:
    """Reads one physical pad.

    The virtual pad the Governor creates is ALSO an XInput device. Reading it
    would echo the companion's output back as "player input". So the slot is
    chosen BEFORE the Governor starts (see pick_player_slot) and passed in.
    """

    def __init__(self, slot: int):
        if not IS_WINDOWS:
            raise RuntimeError("XInput is Windows-only")
        self.slot = slot
        self.name = f"xinput-{slot}"
        self._x = ctypes.windll.xinput1_4

    def read(self) -> GamepadFrame | None:
        s = _XState()
        if self._x.XInputGetState(self.slot, ctypes.byref(s)) != 0:
            return None
        return xinput_state_to_frame(s.buttons, s.lt, s.rt, s.lx, s.ly, s.rx, s.ry)


def pick_player_slot(occupied_before_virtual_pad: list[int]) -> int:
    """Exactly one physical pad must be connected before the virtual pad exists."""
    if len(occupied_before_virtual_pad) != 1:
        raise RuntimeError(
            f"expected exactly one physical controller before start, found {len(occupied_before_virtual_pad)}"
            " (slots: %s). Connect one pad, or pass --player-slot explicitly." % occupied_before_virtual_pad)
    return occupied_before_virtual_pad[0]


# ---------------------------------------------------------------------------
# Keyboard / adaptive switches (Windows): polled, no hooks installed
# ---------------------------------------------------------------------------

# Virtual-key names accepted in profiles
VK_NAMES = {
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    "SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09, "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    **{f"F{n}": 0x6F + n for n in range(1, 13)},
    **{f"NUM{d}": 0x60 + d for d in range(10)},
}

# Targets a key can drive
KEY_TARGETS = {"LX-", "LX+", "LY-", "LY+", "RX-", "RX+", "RY-", "RY+", "LT", "RT"}


class KeyboardSource:
    """mapping: {"W": "LY+", "SPACE": "SOUTH", ...}; values are button names or KEY_TARGETS."""

    def __init__(self, mapping: dict[str, str], key_state: Callable[[int], bool] | None = None):
        from ..intent import BUTTONS
        self.name = "keyboard"
        self.map: list[tuple[int, str]] = []
        for key, target in mapping.items():
            vk = VK_NAMES.get(str(key).upper())
            if vk is None:
                raise ValueError(f"unknown key: {key}")
            if target not in BUTTONS and target not in KEY_TARGETS:
                raise ValueError(f"unknown target for {key}: {target}")
            self.map.append((vk, target))
        if key_state is None:
            if not IS_WINDOWS:
                raise RuntimeError("keyboard polling is Windows-only (inject key_state for tests)")
            user32 = ctypes.windll.user32
            key_state = lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)
        self._down = key_state

    def read(self) -> GamepadFrame:
        ax = {"LX": 0.0, "LY": 0.0, "RX": 0.0, "RY": 0.0, "LT": 0.0, "RT": 0.0}
        buttons = set()
        for vk, target in self.map:
            if not self._down(vk):
                continue
            if target in ("LT", "RT"):
                ax[target] = 1.0
            elif target in KEY_TARGETS:
                ax[target[:2]] += 1.0 if target[2] == "+" else -1.0
            else:
                buttons.add(target)
        return GamepadFrame(ax["LX"], ax["LY"], ax["RX"], ax["RY"], ax["LT"], ax["RT"], frozenset(buttons))


class FakeSource:
    def __init__(self, frames: list[GamepadFrame | None]):
        self.name = "fake"
        self._frames = list(frames)

    def read(self) -> GamepadFrame | None:
        return self._frames.pop(0) if self._frames else GamepadFrame()


# ---------------------------------------------------------------------------

class PlayerInputLoop:
    def __init__(self, source: InputSource, send: Callable[..., None],
                 presence: Callable[[str], None] | None = None, steady: bool = False,
                 presence_every_s: float = 2.0, clock: Callable[[], float] = time.monotonic):
        self.source = source
        self.send = send
        self.presence = presence
        self.clock = clock
        self.presence_every_s = presence_every_s
        self._last_presence = -1e9
        self._was_active = False
        self.lost = False
        self._filters = ({a: OneEuroFilter(min_cutoff_hz=1.0, beta=0.05) for a in ("lx", "ly", "rx", "ry")}
                         if steady else None)

    def _smooth(self, f: GamepadFrame, t: float) -> GamepadFrame:
        if self._filters is None:
            return f
        v = {a: self._filters[a](getattr(f, a), t) for a in ("lx", "ly", "rx", "ry")}
        return GamepadFrame(v["lx"], v["ly"], v["rx"], v["ry"], f.lt, f.rt, f.buttons)

    def poll(self) -> GamepadFrame | None:
        """One step. Returns the frame sent, or None if nothing was sent."""
        t = self.clock()
        raw = self.source.read()
        if raw is None:                      # device unplugged
            if not self.lost:
                self.lost = True
                if self._was_active:         # release whatever the player was holding
                    self._was_active = False
                    self.send(GamepadFrame())
                    return GamepadFrame()
            return None
        self.lost = False
        f = self._smooth(raw, t)
        active = not is_neutral(raw)
        if active:
            if self.presence and t - self._last_presence >= self.presence_every_s:
                self.presence(self.source.name)
                self._last_presence = t
            self._was_active = True
            claims_fn = getattr(self.source, "claims", None)
            claims = tuple(claims_fn(f)) if claims_fn else ()
            if claims:
                self.send(f, claims)
            else:
                self.send(f)
            return f
        if self._was_active:                 # just let go: one neutral, then quiet
            self._was_active = False
            self.send(GamepadFrame())
            return GamepadFrame()
        return None

    def run(self, hz: float = 120.0, stop: Callable[[], bool] = lambda: False) -> None:
        period = 1.0 / hz
        while not stop():
            t0 = time.perf_counter()
            self.poll()
            time.sleep(max(0.0, period - (time.perf_counter() - t0)))
