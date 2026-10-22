"""Governor rules. Pure logic, no I/O, injectable clock: fully unit-testable.

Rule order (first deny wins):
  1. halted (kill switch)          -> deny everything
  2. stale (older than its TTL)    -> deny
  3. replayed sequence number      -> deny (tracked per producer process)
  4. player packets                -> allow (player always outranks the companion)
  5. player override window        -> deny non-player output while the player is acting
  6. attribution: active delegation required for non-player output
  7. online / competitive mode     -> no full autopilot; player presence required
  8. focus: target window must be in front
  9. confidence floor
 10. rate limit per source
 11. menu buttons stripped from non-player output unless allowed
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..intent import Delegation, IntentPacket, MENU_BUTTONS, Source


@dataclass
class GovernorConfig:
    confidence_floor: float = 0.0
    max_packets_per_sec: float = 30.0          # per non-player source
    player_override_hold_ms: int = 1500        # companion yields this long after any player input
    online_mode: bool = False                  # True = online / competitive game
    presence_timeout_s: float = 20.0           # online: player must have shown presence this recently
    allow_menu_buttons: bool = False           # START/BACK/GUIDE from the companion
    blocked_scopes_online: tuple[str, ...] = ("full_autopilot",)
    require_focus: bool = True
    watchdog_ms: int = 500                     # no allowed packet this long -> neutral output


@dataclass
class Decision:
    allow: bool
    reasons: list[str] = field(default_factory=list)
    packet: IntentPacket | None = None         # possibly modified (e.g. menu buttons stripped)


class _TokenBucket:
    def __init__(self, rate: float, burst: float):
        self.rate, self.burst = rate, burst
        self.tokens, self.last = burst, None

    def take(self, now: float) -> bool:
        if self.last is not None:
            self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class GovernorPolicy:
    def __init__(self, config: GovernorConfig):
        self.cfg = config
        self.halted = False
        self.halt_reason = ""
        self.delegations: dict[str, Delegation] = {}
        self.last_seq: dict[tuple[Source, str], int] = {}
        self.last_player_input: float | None = None
        self.last_presence: float | None = None
        self._buckets: dict[Source, _TokenBucket] = {}

    # ---- state changes (all logged by the Governor) -------------------
    def halt(self, reason: str) -> None:
        self.halted, self.halt_reason = True, reason

    def resume(self) -> None:
        self.halted, self.halt_reason = False, ""

    def grant(self, d: Delegation) -> list[str]:
        if self.cfg.online_mode and d.scope in self.cfg.blocked_scopes_online:
            return [f"scope '{d.scope}' not allowed in online mode"]
        self.delegations[d.id] = d
        return []

    def revoke(self, delegation_id: str | None = None) -> None:
        if delegation_id is None:
            self.delegations.clear()
        else:
            self.delegations.pop(delegation_id, None)

    def note_presence(self, now: float) -> None:
        self.last_presence = now

    # ---- evaluation -----------------------------------------------------
    def evaluate(self, p: IntentPacket, now: float, focused: bool) -> Decision:
        if self.halted:
            return Decision(False, [f"halted: {self.halt_reason}"])

        age_ms = (now - p.created_at) * 1000.0
        if age_ms > p.ttl_ms:
            return Decision(False, [f"stale: {age_ms:.0f} ms > ttl {p.ttl_ms} ms"])

        key = (p.source, p.producer)
        last = self.last_seq.get(key)
        if last is not None and p.seq <= last:
            return Decision(False, [f"replayed or out-of-order seq {p.seq} <= {last}"])
        self.last_seq[key] = p.seq

        if p.source is Source.PLAYER:
            self.last_player_input = now
            self.last_presence = now
            return Decision(True, ["player input"], p)

        # ---- everything below is companion output ----
        if (self.last_player_input is not None
                and (now - self.last_player_input) * 1000.0 < self.cfg.player_override_hold_ms):
            return Decision(False, ["player override active"])

        d = self.delegations.get(p.delegation_id or "")
        if d is None:
            return Decision(False, ["no delegation: companion output needs a player grant"])
        if not d.active(now):
            return Decision(False, [f"delegation '{d.id}' expired"])

        if self.cfg.online_mode:
            if d.scope in self.cfg.blocked_scopes_online:
                return Decision(False, [f"scope '{d.scope}' not allowed in online mode"])
            if self.last_presence is None or now - self.last_presence > self.cfg.presence_timeout_s:
                return Decision(False, ["online mode: player not present"])

        if self.cfg.require_focus and not focused:
            return Decision(False, ["target window not in front"])

        if p.confidence < self.cfg.confidence_floor:
            return Decision(False, [f"confidence {p.confidence:.2f} < floor {self.cfg.confidence_floor:.2f}"])

        bucket = self._buckets.setdefault(
            p.source, _TokenBucket(self.cfg.max_packets_per_sec, max(1.0, self.cfg.max_packets_per_sec / 4)))
        if not bucket.take(now):
            return Decision(False, ["rate limit"])

        reasons = [f"delegation '{d.id}' ({d.scope})"]
        out = p
        if not self.cfg.allow_menu_buttons and any(f.buttons & MENU_BUTTONS for f in p.frames):
            out = IntentPacket(
                seq=p.seq, source=p.source, created_at=p.created_at, ttl_ms=p.ttl_ms,
                frames=tuple(f.without(MENU_BUTTONS) for f in p.frames),
                frame_dt_ms=p.frame_dt_ms, confidence=p.confidence,
                delegation_id=p.delegation_id, player_intent_ref=p.player_intent_ref, note=p.note)
            reasons.append("menu buttons stripped")
        return Decision(True, reasons, out)
