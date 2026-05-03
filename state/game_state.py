# ============================================================
# state/game_state.py — Shared game state container
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class GameState:
    # Vision / detections
    detections:       List[Any] = field(default_factory=list)

    # Combat
    threats_present:  bool  = False
    threat_count:     int   = 0
    health_low:       bool  = False
    alert_active:     bool  = False
    caution_active:   bool  = False

    # GTA-specific
    wanted_level:     int   = 0
    in_vehicle:       bool  = False

    # Navigation
    objective_visible: bool = False

    # Metrics
    fps:              float = 0.0
    last_action:      str   = "wait"
    last_action_ts:   float = 0.0

    def update_from_detections(
        self,
        detections:    List[Any],
        threat_labels: List[str],
        caution_labels:List[str],
    ) -> None:
        self.detections = detections
        labels = {d.label for d in detections}

        threats = [d for d in detections if d.label in threat_labels]
        self.threats_present = len(threats) > 0
        self.threat_count    = len(threats)
        self.caution_active  = any(lbl in labels for lbl in caution_labels)
        self.objective_visible = "objective" in labels

    def to_summary_dict(self) -> dict:
        return {
            "threats_present":   self.threats_present,
            "threat_count":      self.threat_count,
            "health_low":        self.health_low,
            "alert_active":      self.alert_active,
            "caution_active":    self.caution_active,
            "wanted_level":      self.wanted_level,
            "in_vehicle":        self.in_vehicle,
            "objective_visible": self.objective_visible,
            "fps":               round(self.fps, 1),
            "last_action":       self.last_action,
        }
