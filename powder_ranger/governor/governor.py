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
        self._last_allowed: float | None = None
        self._watchdog_neutral = False
        self.running = True
        self.stats = {"allowed": 0, "denied": 0, "bad_signature": 0}
        self.seal_key = seal_key
        self.kill.on_trip(self._on_trip)
        self.log.append("session_start", adapter=adapter.name, config=vars(cfg),
                        **(session_info or {}))

    # ------------------------------------------------------------------
    def _on_trip(self, reason: str) -> None:
        """May run on the hotkey thread: neutral output first, then bookkeeping."""
        with self._out_lock:
            self.adapter.apply(self.motor.hard_neutral())
        self.policy.halt(reason)
        self.policy.revoke()
        self.log.append("kill_switch", reason=reason, delegations_revoked=True)

    def handle_raw(self, key: bytes, raw: bytes) -> None:
        try:
            msg_type, body = verify_message(key, raw)
        except BadSignature as exc:
            self.stats["bad_signature"] += 1
            self.log.append("rejected_message", reason=str(exc))
            return
        self.handle(msg_type, body)

    def handle(self, msg_type: str, body: dict) -> None:
        now = self.clock()
        if msg_type == "intent":
            p = IntentPacket.from_dict(body)
            focused = self.focus()
            d = self.policy.evaluate(p, now, focused)
            self.log.append("intent", allow=d.allow, reasons=d.reasons, source=p.source.value,
                            age_ms=round((now - p.created_at) * 1000.0, 1),
                            seq=p.seq, delegation_id=p.delegation_id,
                            player_intent_ref=p.player_intent_ref, confidence=p.confidence,
                            frames=len(p.frames), note=p.note)
            if d.allow and d.packet is not None:
                self.stats["allowed"] += 1
                self._last_allowed = now
                self._watchdog_neutral = False
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
        if (self._last_allowed is not None and not self._watchdog_neutral
                and (now - self._last_allowed) * 1000.0 > self.cfg.watchdog_ms):
            self.motor.clear()
            self._watchdog_neutral = True
            self.log.append("watchdog", note=f"no approved intent for {self.cfg.watchdog_ms} ms; easing to neutral")
        with self._out_lock:
            frame = self.motor.step(now)
            self.adapter.apply(frame)
        return frame

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
