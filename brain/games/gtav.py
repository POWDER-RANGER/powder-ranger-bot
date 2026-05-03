# ============================================================
# brain/games/gtav.py — GTA V rule-based fast reflex
# ============================================================

from __future__ import annotations

from typing import Dict, Any

from state.game_state import GameState
from utils.logger import setup_logger

log = setup_logger(__name__)


def fast_reflex(state: GameState) -> Dict[str, Any] | None:
    """
    Priority:
    1. Health critically low  → cover
    2. Wanted + in vehicle    → evade
    3. Threats on foot ≥ 3   → cover
    4. Objective clear        → move forward
    """
    if state.health_low:
        log.debug("[GTAV-REFLEX] Health low → cover")
        return {"action": "cover", "duration": 2.0}

    if state.wanted_level >= 2 and state.in_vehicle:
        log.debug("[GTAV-REFLEX] Wanted + vehicle → evade")
        return {"action": "sprint", "direction": "forward", "duration": 2.0}

    if state.threats_present and not state.in_vehicle and state.threat_count >= 3:
        log.debug("[GTAV-REFLEX] Multiple threats on foot → cover")
        return {"action": "cover", "duration": 1.5}

    if state.objective_visible and not state.threats_present:
        log.debug("[GTAV-REFLEX] Objective clear → move forward")
        return {"action": "move", "direction": "forward", "duration": 1.0}

    return None


def enrich_prompt_context(state: GameState) -> str:
    lines = [f"wanted_level: {state.wanted_level}"]
    if state.in_vehicle:
        lines.append("player is currently INSIDE a vehicle")
    if state.alert_active:
        lines.append("ALERT: police/enemy is actively pursuing")
    return "\n".join(lines)
