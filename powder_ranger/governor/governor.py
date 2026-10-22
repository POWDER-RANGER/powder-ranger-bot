"""The Governor: the single path between every decision-maker and the controller.

It runs as its own process. It owns the output adapter; nothing else may.
Messages arrive over a localhost-only ZMQ PULL socket, HMAC-signed with the
session key the launcher created. Every decision is written to the
hash-chained intent log.

Message types (body fields):
  intent    IntentPacket.to_dict()
  grant     Delegation.to_dict()          player grants leeway
  revoke    {"id": str | None}            None = revoke all
  presence  {"how": "voice"|"gaze"|...}   player is here (online-mode check)
  command   {"id", "verb", "target", ...}  a player instruction, logged for attribution
  halt      {"reason": str}
  resume    {}
  shutdown  {}
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from ..intent import BadSignature, Delegation, GamepadFrame, IntentPacket, verify_message
from ..motor.model import MotorModel
from ..output.adapters import OutputAdapter
from .intent_log import IntentLog
from .policy import GovernorConfig, GovernorPolicy
from .safety import KillSwitch


class Governor:
    def __init__(self, cfg: GovernorConfig, motor: MotorModel, adapter: OutputAdapter,
                 log: IntentLog, killswitch: KillSwitch, focus: Callable[[], bool],
                 clock: Callable[[], float] = time.monotonic,
                 seal_key: bytes | None = None, session_info: dict | None = None):
        self.cfg = cfg
        self.policy = GovernorPolicy(cfg)
        self.motor = motor
        self.adapter = adapter
        self.log = log
        self.kill = killswitch
        self.focus = focus
        self.clock = clock
        self._out_lock = threading.Lock()
        self._claims: dict[str, tuple[object, float]] = {}   # control -> (player value, time)
        self._watchdog_neutral = False
        self.running = True
        self.stats = {"allowed": 0, "denied": 0, "bad_signature": 0, "malformed": 0}
        self.seal_key = seal_key
        self.kill.on_trip(self._on_trip)
        self.log.append("session_start", adapter=adapter.name, config=vars(cfg),
                        **(session_info or {}))

    # ------------------------------------------------------------------
    def _on_trip(self, reason: str) -> None:
        """May run on the hotkey thread: latch the halt first so no packet can be accepted
        while the neutral frame is being written, then zero the output, then log."""
        self.policy.halt(reason)
        self.policy.revoke()
        with self._out_lock:
            self._claims.clear()
            self.adapter.apply(self.motor.hard_neutral())
        self.log.append("kill_switch", reason=reason, delegations_revoked=True)

    def handle_raw(self, key: bytes, raw: bytes) -> None:
        try:
            msg_type, body = verify_message(key, raw)
        except BadSignature as exc:
            self.stats["bad_signature"] += 1
            self.log.append("rejected_message", reason=str(exc))
            return
        try:
            self.handle(msg_type, body)
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError) as exc:
            self.stats["malformed"] += 1
            self.log.append("rejected_message", reason=f"malformed {msg_type}: {type(exc).__name__}: {exc}")

    def handle(self, msg_type: str, body: dict) -> None:
        now = self.clock()
        if msg_type == "intent":
            p = IntentPacket.from_dict(body)
            focused = self.focus()
            d = self.policy.evaluate(p, now, focused)
            self.log.append("intent", allow=d.allow, reasons=d.reasons, source=p.source.value,
                            age_ms=round((now - p.created_at) * 1000.0, 1),
                            seq=p.seq, producer=p.producer, claims=list(p.claims), delegation_id=p.delegation_id,
                            player_intent_ref=p.player_intent_ref, confidence=p.confidence,
                            frames=len(p.frames), note=p.note)
            if d.allow and d.packet is not None and d.packet.claims:
                self.stats["allowed"] += 1
                f = d.packet.frames[-1]
                for c in d.packet.claims:
                    self._claims[c] = (f.buttons if c == "buttons" else getattr(f, c), now)
            elif d.allow and d.packet is not None:
                self.stats["allowed"] += 1
                self._watchdog_neutral = False
                if d.packet.source.value == "player":
                    self._claims.clear()                 # full takeover supersedes partial claims
                self.motor.schedule(d.packet.frames, d.packet.frame_dt_ms, d.packet.source, now)
            else:
                self.stats["denied"] += 1
        elif msg_type == "grant":
            dl = Delegation.from_dict(body)
            problems = self.policy.grant(dl)
            self.log.append("grant", delegation=dl.to_dict(), refused=problems)
        elif msg_type == "revoke":
            self.policy.revoke(body.get("id"))
            self.motor.clear()
            self.log.append("revoke", id=body.get("id"))
        elif msg_type == "presence":
            self.policy.note_presence(now)
        elif msg_type == "command":
            # A player instruction (voice, gaze, switch). Logged so later output can cite it.
            self.policy.note_presence(now)
            self.log.append("player_command", **{k: body.get(k) for k in
                                                 ("id", "verb", "target", "manner", "scope", "text", "via")})
        elif msg_type == "halt":
            self.kill.trip(body.get("reason", "halt message"))
        elif msg_type == "resume":
            self._resume("resume message")
        elif msg_type == "shutdown":
            self.running = False
            self.log.append("shutdown_requested")
        else:
            self.log.append("unknown_message", msg_type=msg_type)

    def _resume(self, how: str) -> None:
        if self.kill.tripped or self.policy.halted:
            self.kill.clear()
            self.policy.resume()
            self.log.append("resume", how=how, note="delegations stay revoked; the player must grant again")

    def tick(self) -> GamepadFrame:
        now = self.clock()
        self.kill.poll_stop_file()
        if self.kill.take_resume_request():
            self._resume("resume hotkey")
        if self.policy.halted:
            with self._out_lock:
                frame = GamepadFrame.neutral()
                self.adapter.apply(frame)
            return frame
        # The watchdog watches what was actually played, not what arrived: a long chunk keeps
        # it quiet while it plays out, and packets that produce no frames cannot keep a held
        # value alive.
        last = self.motor.last_played
        if (last is not None and not self._watchdog_neutral and not self.motor.pending()
                and (now - last) * 1000.0 > self.cfg.watchdog_ms):
            self.motor.clear()
            self._watchdog_neutral = True
            self.log.append("watchdog", note=f"no output played for {self.cfg.watchdog_ms} ms; easing to neutral")
        with self._out_lock:
            frame = self._merge_claims(self.motor.step(now), now)
            self.adapter.apply(frame)
        return frame

    def _merge_claims(self, f: GamepadFrame, now: float) -> GamepadFrame:
        ttl = self.cfg.claim_ttl_ms / 1000.0
        live = {c: v for c, (v, t) in self._claims.items() if now - t <= ttl}
        for c in [c for c in self._claims if c not in live]:
            del self._claims[c]
        if not live:
            return f
        vals = {a: live.get(a, getattr(f, a)) for a in ("lx", "ly", "rx", "ry", "lt", "rt")}
        return GamepadFrame(**vals, buttons=live.get("buttons", f.buttons))

    def close(self) -> None:
        """Always leaves the controller neutral, even if the adapter misbehaves."""
        try:
            with self._out_lock:
                self.adapter.apply(self.motor.hard_neutral())
                self.adapter.close()
        finally:
            self.log.append("session_end", stats=self.stats)
            self.log.close(seal_key=self.seal_key)

    # ------------------------------------------------------------------
    def serve(self, endpoint: str, key: bytes, tick_hz: float = 120.0) -> None:
        """Main loop. endpoint must be a localhost address."""
        import zmq
        if not (endpoint.startswith("tcp://127.0.0.1:") or endpoint.startswith("ipc://")):
            raise ValueError("the Governor only listens on localhost")
        ctx = zmq.Context()
        sock = ctx.socket(zmq.PULL)
        sock.bind(endpoint)
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        period = 1.0 / tick_hz
        next_tick = self.clock()
        try:
            while self.running:
                timeout_ms = max(0, int((next_tick - self.clock()) * 1000))
                events = dict(poller.poll(timeout_ms))
                while sock in events:
                    try:
                        raw = sock.recv(flags=zmq.NOBLOCK)
                    except zmq.Again:
                        break
                    self.handle_raw(key, raw)
                if self.clock() >= next_tick:
                    self.tick()
                    next_tick += period
                    if next_tick < self.clock():          # fell behind: do not burst
                        next_tick = self.clock() + period
        finally:
            self.close()
            sock.close(0)
            ctx.term()
