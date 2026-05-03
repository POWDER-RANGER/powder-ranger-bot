# ============================================================
# brain/games/mgs5.py — MGS5 rule-based fast reflex
# ============================================================

from __future__ import annotations

from typing import Dict, Any, List

from state.game_state import GameState
from vision.vision import Detection
from utils.logger import setup_logger

log = setup_logger(__name__)


def fast_reflex(state: GameState, detections: List[Detection]) -> Dict[str, Any] | None:
    label_set = {d.label for d in detections}

    if state.alert_active or "alert_indicator" in label_set:
        log.debug("[MGS5-REFLEX] Alert → prone + stop")
        return {"action": "prone", "direction": "stop", "duration": 2.0}

    cones        = [d for d in detections if d.label == "guard_cone_vision"]
    frame_center = (960, 540)
    for cone in cones:
        x1, y1, x2, y2 = cone.bbox
        if x1 < frame_center[0] < x2 and y1 < frame_center[1] < y2:
            log.debug("[MGS5-REFLEX] Inside vision cone → evade left")
            return {"action": "cover_move", "direction": "left", "duration": 1.0}

    if state.caution_active:
        log.debug("[MGS5-REFLEX] Caution → crouch hold")
        return {"action": "crouch", "direction": "stop", "duration": 1.0}

    guards = [d for d in detections if d.label == "guard"]
    if len(guards) == 1 and not state.alert_active and not state.caution_active:
        g = guards[0]
        log.debug(f"[MGS5-REFLEX] Isolated guard at {g.center} → fulton")
        return {"action": "fulton", "target_x": g.center[0], "target_y": g.center[1]}

    if state.objective_visible and not state.threats_present and not state.caution_active:
        log.debug("[MGS5-REFLEX] Objective clear → crouch forward")
        return {"action": "crouch", "direction": "forward", "duration": 1.5}

    return None


def enrich_prompt_context(state: GameState, detections: List[Detection]) -> str:
    guard_count = sum(1 for d in detections if "guard" in d.label)
    lines = [
        f"guard_count: {guard_count}",
        f"alert_active: {state.alert_active}",
        f"caution_active: {state.caution_active}",
    ]
    if state.health_low:
        lines.append("health critically low — avoid engagement")
    return "\n".join(lines)
