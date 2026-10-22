"""Intent packets: the only message type that can ask for controller output.

Every request to move a stick or press a button travels as an IntentPacket.
Packets are plain JSON on the wire (never pickle) and are HMAC-signed with a
per-session key, so only processes started by the launcher can submit them.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Iterable

# Unified button names. These follow NitroGen's naming so policy output maps 1:1.
BUTTONS: tuple[str, ...] = (
    "SOUTH", "EAST", "WEST", "NORTH",
    "LEFT_SHOULDER", "RIGHT_SHOULDER",
    "LEFT_THUMB", "RIGHT_THUMB",
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
    "START", "BACK", "GUIDE",
)
MENU_BUTTONS: frozenset[str] = frozenset({"START", "BACK", "GUIDE"})


class Source(str, Enum):
    """Who produced a packet. PLAYER always outranks everything else."""

    PLAYER = "player"          # the human in the loop (any input adapter)
    REFLEX = "reflex"          # fast policy, e.g. NitroGen
    PLANNER = "planner"        # strategic layers
    SYSTEM = "system"          # launcher / test scripts acting for the player


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


@dataclass(frozen=True)
class GamepadFrame:
    """One controller state. Sticks in [-1, 1] with +y = up (XInput convention).
    Triggers in [0, 1]."""

    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    lt: float = 0.0
    rt: float = 0.0
    buttons: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        for name in ("lx", "ly", "rx", "ry"):
            object.__setattr__(self, name, _clamp(float(getattr(self, name)), -1.0, 1.0))
        for name in ("lt", "rt"):
            object.__setattr__(self, name, _clamp(float(getattr(self, name)), 0.0, 1.0))
        unknown = set(self.buttons) - set(BUTTONS)
        if unknown:
            raise ValueError(f"unknown buttons: {sorted(unknown)}")
        object.__setattr__(self, "buttons", frozenset(self.buttons))

    @staticmethod
    def neutral() -> "GamepadFrame":
        return GamepadFrame()

    def without(self, buttons: Iterable[str]) -> "GamepadFrame":
        return GamepadFrame(self.lx, self.ly, self.rx, self.ry, self.lt, self.rt,
                            self.buttons - frozenset(buttons))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["buttons"] = sorted(self.buttons)
        return d

    @staticmethod
    def from_dict(d: dict) -> "GamepadFrame":
        return GamepadFrame(
            lx=d.get("lx", 0.0), ly=d.get("ly", 0.0),
            rx=d.get("rx", 0.0), ry=d.get("ry", 0.0),
            lt=d.get("lt", 0.0), rt=d.get("rt", 0.0),
            buttons=frozenset(d.get("buttons", ())),
        )


@dataclass(frozen=True)
class IntentPacket:
    """A request for controller output.

    frames: a short sequence played back at frame_dt_ms intervals.
    delegation_id: required for non-player sources; names the delegation the
        player granted that authorises this output.
    player_intent_ref: optional id of the player command this packet serves.
    """

    seq: int
    source: Source
    created_at: float                 # sender's clock, seconds (time.monotonic on the same machine)
    ttl_ms: int
    frames: tuple[GamepadFrame, ...]
    frame_dt_ms: float = 1000.0 / 60.0
    confidence: float = 1.0
    delegation_id: str | None = None
    player_intent_ref: str | None = None
    note: str = ""
    producer: str = ""                # one id per sending process; replay checks are per producer

    def to_dict(self) -> dict:
        return {
            "producer": self.producer,
            "seq": self.seq,
            "source": self.source.value,
            "created_at": self.created_at,
            "ttl_ms": self.ttl_ms,
            "frames": [f.to_dict() for f in self.frames],
            "frame_dt_ms": self.frame_dt_ms,
            "confidence": self.confidence,
            "delegation_id": self.delegation_id,
            "player_intent_ref": self.player_intent_ref,
            "note": self.note,
        }

    @staticmethod
    def from_dict(d: dict) -> "IntentPacket":
        return IntentPacket(
            seq=int(d["seq"]),
            source=Source(d["source"]),
            created_at=float(d["created_at"]),
            ttl_ms=int(d["ttl_ms"]),
            frames=tuple(GamepadFrame.from_dict(f) for f in d["frames"]),
            frame_dt_ms=float(d.get("frame_dt_ms", 1000.0 / 60.0)),
            confidence=float(d.get("confidence", 1.0)),
            delegation_id=d.get("delegation_id"),
            player_intent_ref=d.get("player_intent_ref"),
            note=d.get("note", ""),
            producer=str(d.get("producer", "")),
        )


@dataclass(frozen=True)
class Delegation:
    """A grant of leeway from the player to the companion.

    scope examples: "full_autopilot", "driving", "routine", "combat".
    expires_at: monotonic seconds, or None for until-revoked.
    """

    id: str
    scope: str
    granted_at: float
    expires_at: float | None = None
    note: str = ""

    def active(self, now: float) -> bool:
        return self.expires_at is None or now < self.expires_at

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Delegation":
        return Delegation(id=d["id"], scope=d["scope"], granted_at=float(d["granted_at"]),
                          expires_at=d.get("expires_at"), note=d.get("note", ""))


# --------------------------------------------------------------------------
# Wire format: {"type": ..., "body": {...}, "mac": hex}
# --------------------------------------------------------------------------

def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sign_message(key: bytes, msg_type: str, body: dict) -> bytes:
    payload = {"type": msg_type, "body": body}
    mac = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    payload["mac"] = mac
    return _canonical(payload)


class BadSignature(Exception):
    pass


def verify_message(key: bytes, raw: bytes) -> tuple[str, dict]:
    try:
        payload = json.loads(raw)
        mac = payload.pop("mac")
        msg_type = payload["type"]
        body = payload["body"]
    except (ValueError, KeyError, TypeError) as exc:
        raise BadSignature(f"malformed message: {exc}") from exc
    expected = hmac.new(key, _canonical({"type": msg_type, "body": body}), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        raise BadSignature("signature mismatch")
    return msg_type, body
