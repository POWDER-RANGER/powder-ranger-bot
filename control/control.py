# ============================================================
# control/control.py — pydirectinput action executor
# ============================================================

from __future__ import annotations

import time
from typing import Dict, Any

import pydirectinput

from utils.logger import setup_logger

log = setup_logger(__name__)

KEY_MAP: Dict[str, list] = {
    "move":       ["w"],
    "sprint":     ["shift", "w"],
    "cover":      ["q"],
    "crouch":     ["c"],
    "prone":      ["z"],
    "cover_move": ["q"],
    "fulton":     ["e"],
    "attack":     [],           # mouse1 — handled separately
    "wait":       [],
    "idle":       [],
}

DIRECTION_MAP: Dict[str, str] = {
    "forward":  "w",
    "backward": "s",
    "left":     "a",
    "right":    "d",
    "stop":     "",
}


class Controller:
    def __init__(
        self,
        bindings:          Dict = None,
        mouse_sensitivity: float = 0.45,
        max_duration:      float = 2.5,
        dry_run:           bool  = False,
    ):
        self.bindings          = bindings or {}
        self.mouse_sensitivity = mouse_sensitivity
        self.max_duration      = max_duration
        self.dry_run           = dry_run

    def execute(self, action: Dict[str, Any]) -> None:
        act_name = action.get("action", "wait")
        duration = min(float(action.get("duration", 0.1)), self.max_duration)
        direction= action.get("direction", "")

        if self.dry_run:
            log.debug(f"[DRY-RUN] action={act_name} dir={direction} dur={duration:.2f}s")
            time.sleep(min(duration, 0.05))
            return

        keys = list(KEY_MAP.get(act_name, []))
        if direction and direction in DIRECTION_MAP and DIRECTION_MAP[direction]:
            dir_key = DIRECTION_MAP[direction]
            if dir_key not in keys:
                keys.append(dir_key)

        for k in keys:
            pydirectinput.keyDown(k)
        time.sleep(duration)
        for k in reversed(keys):
            pydirectinput.keyUp(k)
