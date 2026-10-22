"""Output adapters: the last step before the game. Only the Governor holds one.

DryRunAdapter   records frames (tests, rehearsal without a game)
VGamepadAdapter virtual Xbox 360 or DualShock 4 via ViGEmBus (Windows)

A future PicoHIDAdapter (hardware USB controller over serial) implements the
same three methods.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from ..intent import GamepadFrame


class OutputAdapter(ABC):
    name = "abstract"

    @abstractmethod
    def apply(self, frame: GamepadFrame) -> None: ...

    def neutral(self) -> None:
        self.apply(GamepadFrame.neutral())

    def close(self) -> None:
        self.neutral()


class DryRunAdapter(OutputAdapter):
    name = "dryrun"

    def __init__(self, record_path: str | Path | None = None, keep: int = 10000):
        self.frames: list[GamepadFrame] = []
        self.keep = keep
        self._fh = Path(record_path).open("a", encoding="utf-8") if record_path else None

    def apply(self, frame: GamepadFrame) -> None:
        self.frames.append(frame)
        if len(self.frames) > self.keep:
            del self.frames[: len(self.frames) - self.keep]
        if self._fh:
            self._fh.write(json.dumps(frame.to_dict()) + "\n")

    def close(self) -> None:
        super().close()
        if self._fh:
            self._fh.close()


# ---------------------------------------------------------------------------
# vgamepad (ViGEmBus). Imported lazily so the package works without it.
# ---------------------------------------------------------------------------

_X360_BUTTONS = {
    "SOUTH": "XUSB_GAMEPAD_A", "EAST": "XUSB_GAMEPAD_B",
    "WEST": "XUSB_GAMEPAD_X", "NORTH": "XUSB_GAMEPAD_Y",
    "LEFT_SHOULDER": "XUSB_GAMEPAD_LEFT_SHOULDER", "RIGHT_SHOULDER": "XUSB_GAMEPAD_RIGHT_SHOULDER",
    "LEFT_THUMB": "XUSB_GAMEPAD_LEFT_THUMB", "RIGHT_THUMB": "XUSB_GAMEPAD_RIGHT_THUMB",
    "DPAD_UP": "XUSB_GAMEPAD_DPAD_UP", "DPAD_DOWN": "XUSB_GAMEPAD_DPAD_DOWN",
    "DPAD_LEFT": "XUSB_GAMEPAD_DPAD_LEFT", "DPAD_RIGHT": "XUSB_GAMEPAD_DPAD_RIGHT",
    "START": "XUSB_GAMEPAD_START", "BACK": "XUSB_GAMEPAD_BACK", "GUIDE": "XUSB_GAMEPAD_GUIDE",
}

_DS4_BUTTONS = {
    "SOUTH": "DS4_BUTTON_CROSS", "EAST": "DS4_BUTTON_CIRCLE",
    "WEST": "DS4_BUTTON_SQUARE", "NORTH": "DS4_BUTTON_TRIANGLE",
    "LEFT_SHOULDER": "DS4_BUTTON_SHOULDER_LEFT", "RIGHT_SHOULDER": "DS4_BUTTON_SHOULDER_RIGHT",
    "LEFT_THUMB": "DS4_BUTTON_THUMB_LEFT", "RIGHT_THUMB": "DS4_BUTTON_THUMB_RIGHT",
    "START": "DS4_BUTTON_OPTIONS", "BACK": "DS4_BUTTON_SHARE",
}

# (up, down, left, right) -> DS4_DPAD_DIRECTIONS member
_DS4_DPAD = {
    (False, False, False, False): "DS4_BUTTON_DPAD_NONE",
    (True, False, False, False): "DS4_BUTTON_DPAD_NORTH",
    (False, True, False, False): "DS4_BUTTON_DPAD_SOUTH",
    (False, False, True, False): "DS4_BUTTON_DPAD_WEST",
    (False, False, False, True): "DS4_BUTTON_DPAD_EAST",
    (True, False, True, False): "DS4_BUTTON_DPAD_NORTHWEST",
    (True, False, False, True): "DS4_BUTTON_DPAD_NORTHEAST",
    (False, True, True, False): "DS4_BUTTON_DPAD_SOUTHWEST",
    (False, True, False, True): "DS4_BUTTON_DPAD_SOUTHEAST",
}


def ds4_dpad_key(buttons: frozenset[str]) -> tuple[bool, bool, bool, bool]:
    up, down = "DPAD_UP" in buttons, "DPAD_DOWN" in buttons
    left, right = "DPAD_LEFT" in buttons, "DPAD_RIGHT" in buttons
    if up and down:          # impossible on a real pad: cancel out
        up = down = False
    if left and right:
        left = right = False
    return up, down, left, right


class VGamepadAdapter(OutputAdapter):
    """Virtual controller through vgamepad.

    invert_y: vgamepad's float joystick API is expected to take +y = up for
    both pad types. The pad test (`powder-ranger padtest`) confirms this on the
    real machine; set invert_y if the game sees up and down swapped.
    """

    def __init__(self, kind: str = "x360", invert_y: bool = False):
        import vgamepad as vg  # Windows + ViGEmBus required
        self.vg = vg
        self.kind = kind
        self.invert_y = invert_y
        if kind == "x360":
            self.pad = vg.VX360Gamepad()
            self.name = "vgamepad-x360"
        elif kind == "ds4":
            self.pad = vg.VDS4Gamepad()
            self.name = "vgamepad-ds4"
        else:
            raise ValueError("kind must be 'x360' or 'ds4'")

    def apply(self, f: GamepadFrame) -> None:
        vg, pad = self.vg, self.pad
        pad.reset()
        sy = -1.0 if self.invert_y else 1.0
        if self.kind == "x360":
            for b in f.buttons:
                pad.press_button(button=getattr(vg.XUSB_BUTTON, _X360_BUTTONS[b]))
        else:
            for b in f.buttons:
                if b in _DS4_BUTTONS:
                    pad.press_button(button=getattr(vg.DS4_BUTTONS, _DS4_BUTTONS[b]))
            if "GUIDE" in f.buttons:
                pad.press_special_button(special_button=vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_PS)
            pad.directional_pad(direction=getattr(vg.DS4_DPAD_DIRECTIONS, _DS4_DPAD[ds4_dpad_key(f.buttons)]))
        pad.left_joystick_float(x_value_float=f.lx, y_value_float=sy * f.ly)
        pad.right_joystick_float(x_value_float=f.rx, y_value_float=sy * f.ry)
        pad.left_trigger_float(value_float=f.lt)
        pad.right_trigger_float(value_float=f.rt)
        pad.update()


def make_adapter(kind: str, record_path: str | Path | None = None, invert_y: bool = False) -> OutputAdapter:
    if kind == "dryrun":
        return DryRunAdapter(record_path)
    if kind in ("x360", "ds4"):
        return VGamepadAdapter(kind, invert_y=invert_y)
    raise ValueError(f"unknown output adapter: {kind}")
