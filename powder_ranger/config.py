"""Configuration: config/default.yaml, overlaid by an optional player profile."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

from .governor.policy import GovernorConfig
from .motor.model import MotorProfile

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"


@dataclass
class Settings:
    endpoint: str = "tcp://127.0.0.1:5577"
    tick_hz: float = 120.0
    log_dir: str = "logs"
    stop_file: str = str(Path.home() / ".powder_ranger" / "STOP")
    output: str = "x360"
    invert_y: bool = False
    governor: GovernorConfig = field(default_factory=GovernorConfig)
    motor: MotorProfile = field(default_factory=MotorProfile)
    profile_name: str = "default"
    mode: str = "deployment"          # deployment | development


# Human-limit bounds every deployment session must satisfy. Development mode may
# go outside them, but only in isolation (never with online_mode).
DEPLOYMENT_BOUNDS = {
    "motor.reaction_min_ms": (">=", 100.0),
    "motor.max_presses_per_sec": ("<=", 12.0),
    "motor.button_min_hold_ms": (">=", 30.0),
    "motor.humanize": ("==", True),
    "motor.episode_gap_ms": ("<=", 1000.0),
    "governor.max_packets_per_sec": ("<=", 60.0),
    "governor.require_focus": ("==", True),
}


def validate_settings(s: Settings, output: str | None = None) -> list[str]:
    """Problems that must block a session from starting. Empty list = OK."""
    problems: list[str] = []
    if s.mode not in ("deployment", "development"):
        return [f"unknown mode '{s.mode}'"]
    if s.governor.online_mode and "full_autopilot" not in s.governor.blocked_scopes_online:
        problems.append("online_mode requires full_autopilot in blocked_scopes_online")
    if s.mode == "development":
        if s.governor.online_mode:
            problems.append("development mode runs isolated only: online_mode must be false")
        return problems
    for key, (op, bound) in DEPLOYMENT_BOUNDS.items():
        section, name = key.split(".")
        value = getattr(s.motor if section == "motor" else s.governor, name)
        ok = {">=": value >= bound, "<=": value <= bound, "==": value == bound}[op]
        if not ok:
            problems.append(f"deployment bound: {key} = {value} (must be {op} {bound})")
    return problems


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_settings(config_path: str | Path | None = None, profile_path: str | Path | None = None) -> Settings:
    raw = yaml.safe_load(Path(config_path or DEFAULT_CONFIG).read_text()) or {}
    profile_name = "default"
    if profile_path:
        prof = yaml.safe_load(Path(profile_path).read_text()) or {}
        profile_name = prof.pop("name", Path(profile_path).stem)
        raw = _merge(raw, prof)

    gov_fields = {f.name for f in fields(GovernorConfig)}
    gov_raw = raw.get("governor", {}) or {}
    unknown = set(gov_raw) - gov_fields
    if unknown:
        raise ValueError(f"unknown governor settings: {sorted(unknown)}")
    if "blocked_scopes_online" in gov_raw:
        gov_raw["blocked_scopes_online"] = tuple(gov_raw["blocked_scopes_online"])
    if gov_raw.get("allowed_scopes") is not None:
        gov_raw["allowed_scopes"] = tuple(gov_raw["allowed_scopes"])

    s = Settings(
        endpoint=raw.get("endpoint", Settings.endpoint),
        tick_hz=float(raw.get("tick_hz", Settings.tick_hz)),
        log_dir=raw.get("log_dir", Settings.log_dir),
        stop_file=str(Path(raw.get("stop_file", Settings.stop_file)).expanduser().resolve()),
        output=raw.get("output", Settings.output),
        invert_y=bool(raw.get("invert_y", False)),
        governor=GovernorConfig(**gov_raw),
        motor=MotorProfile.from_dict(raw.get("motor")),
        profile_name=profile_name,
        mode=raw.get("mode", "deployment"),
    )
    return s
