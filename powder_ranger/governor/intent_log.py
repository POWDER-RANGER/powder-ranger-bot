"""Append-only, hash-chained intent log.

Each line is a JSON record carrying the hash of the previous record, so an
edit, deletion or reordering inside the log breaks verification. This is the
evidence that every controller output traced to a player intent or delegation.

Limits, stated plainly:
  - A hash chain alone cannot detect truncation (lines cut off the end) and
    cannot prove who wrote the log; anyone can build a fresh valid chain.
  - seal() writes <log>.seal: record count + last hash + an HMAC made with a
    key stored on this machine. With the seal, truncation and regeneration by
    someone without that key are detected. Someone holding the key can still
    forge both. Keep the key file private.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _digest(prev_hash: str, record: dict) -> str:
    body = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


class IntentLog:
    def __init__(self, path: str | Path, wall_clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._wall = wall_clock
        self._prev = GENESIS
        self._count = 0
        if self.path.exists() and self.path.stat().st_size > 0:
            ok, n, last, problem = verify_log(self.path)
            if not ok:
                raise RuntimeError(f"refusing to append to a broken log: {problem}")
            self._prev, self._count = last, n
        self._lock = threading.Lock()
        self._fh = self.path.open("a", encoding="utf-8")

    @property
    def count(self) -> int:
        return self._count

    def append(self, kind: str, **fields: Any) -> str:
        """Thread-safe: the kill-switch hotkey thread writes here too."""
        with self._lock:
            record = {"n": self._count, "t_wall": self._wall(), "kind": kind, **fields}
            record = json.loads(json.dumps(record, default=str))   # exactly what verify will see
            h = _digest(self._prev, record)
            line = json.dumps({"prev": self._prev, "hash": h, "record": record},
                              sort_keys=True, separators=(",", ":"), default=str)
            self._fh.write(line + "\n")
            self._fh.flush()
            self._prev = h
            self._count += 1
            return h

    def seal(self, key: bytes) -> Path:
        with self._lock:
            body = {"count": self._count, "last_hash": self._prev, "log": self.path.name}
            body["mac"] = hmac.new(key, json.dumps(body, sort_keys=True).encode(), hashlib.sha256).hexdigest()
            seal_path = self.path.with_suffix(self.path.suffix + ".seal")
            seal_path.write_text(json.dumps(body, sort_keys=True))
            return seal_path

    def close(self, seal_key: bytes | None = None) -> None:
        if seal_key is not None:
            self.seal(seal_key)
        if not self._fh.closed:
            self._fh.close()


def load_or_create_log_key(path: str | Path | None = None) -> bytes:
    """Machine-local key for sealing logs (~/.powder_ranger/log.key)."""
    p = Path(path) if path else Path.home() / ".powder_ranger" / "log.key"
    if p.exists():
        return bytes.fromhex(p.read_text().strip())
    p.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    p.write_text(key.hex())
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return key


def verify_seal(path: str | Path, key: bytes) -> tuple[bool, str]:
    """Check <log>.seal against the log. Run verify_log first."""
    path = Path(path)
    seal_path = path.with_suffix(path.suffix + ".seal")
    if not seal_path.exists():
        return False, "no seal file (session may have ended abnormally, or the seal was removed)"
    try:
        seal = json.loads(seal_path.read_text())
        mac = seal.pop("mac")
    except (ValueError, KeyError) as exc:
        return False, f"seal unreadable: {exc}"
    expected = hmac.new(key, json.dumps(seal, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return False, "seal signature mismatch"
    ok, n, last, problem = verify_log(path)
    if not ok:
        return False, f"log chain invalid: {problem}"
    if n != seal["count"] or last != seal["last_hash"]:
        return False, f"log does not match seal: {n} records vs sealed {seal['count']} (truncated or extended)"
    return True, ""


def verify_log(path: str | Path) -> tuple[bool, int, str, str]:
    """Returns (ok, record_count, last_hash, problem)."""
    prev = GENESIS
    n = 0
    with Path(path).open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                record, claimed, claimed_prev = entry["record"], entry["hash"], entry["prev"]
            except (ValueError, KeyError) as exc:
                return False, n, prev, f"line {lineno}: unreadable ({exc})"
            if claimed_prev != prev:
                return False, n, prev, f"line {lineno}: chain broken (prev mismatch)"
            if record.get("n") != n:
                return False, n, prev, f"line {lineno}: record number {record.get('n')} != {n}"
            if _digest(prev, record) != claimed:
                return False, n, prev, f"line {lineno}: hash mismatch (record altered)"
            prev = claimed
            n += 1
    return True, n, prev, ""
