"""Client side of the Governor channel. Every producer (policy runner, input
adapters, launcher) talks to the Governor through this, and only this."""

from __future__ import annotations

import itertools
import time

from ..intent import Delegation, GamepadFrame, IntentPacket, Source, sign_message


class GovernorClient:
    def __init__(self, endpoint: str, key: bytes, source: Source, clock=time.monotonic):
        import zmq
        self._zmq = zmq
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUSH)
        self._sock.setsockopt(zmq.LINGER, 500)
        self._sock.setsockopt(zmq.SNDHWM, 64)
        self._sock.connect(endpoint)
        self.key = key
        self.source = source
        self.clock = clock
        # Start sequence numbers from the clock so a restarted producer is never
        # mistaken for a replay of the old one.
        self._seq = itertools.count(int(time.time() * 1000))

    def _send(self, msg_type: str, body: dict) -> None:
        self._sock.send(sign_message(self.key, msg_type, body))

    def send_frames(self, frames: list[GamepadFrame] | tuple[GamepadFrame, ...], *,
                    frame_dt_ms: float, ttl_ms: int = 250, confidence: float = 1.0,
                    delegation_id: str | None = None, player_intent_ref: str | None = None,
                    note: str = "") -> int:
        seq = next(self._seq)
        p = IntentPacket(seq=seq, source=self.source, created_at=self.clock(), ttl_ms=ttl_ms,
                         frames=tuple(frames), frame_dt_ms=frame_dt_ms, confidence=confidence,
                         delegation_id=delegation_id, player_intent_ref=player_intent_ref, note=note)
        self._send("intent", p.to_dict())
        return seq

    def grant(self, d: Delegation) -> None:
        self._send("grant", d.to_dict())

    def revoke(self, delegation_id: str | None = None) -> None:
        self._send("revoke", {"id": delegation_id})

    def presence(self, how: str) -> None:
        self._send("presence", {"how": how})

    def halt(self, reason: str) -> None:
        self._send("halt", {"reason": reason})

    def resume(self) -> None:
        self._send("resume", {})

    def shutdown(self) -> None:
        self._send("shutdown", {})

    def close(self) -> None:
        self._sock.close()
