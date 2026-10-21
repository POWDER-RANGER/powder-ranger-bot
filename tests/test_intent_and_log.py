import json

import pytest

from powder_ranger.governor.intent_log import IntentLog, verify_log, verify_seal
from powder_ranger.intent import (BadSignature, GamepadFrame, IntentPacket, Source,
                                  sign_message, verify_message)

KEY = b"k" * 32


def test_frame_clamps_and_rejects_unknown_buttons():
    f = GamepadFrame(lx=3, ly=-9, lt=2, rt=-1)
    assert (f.lx, f.ly, f.lt, f.rt) == (1.0, -1.0, 1.0, 0.0)
    with pytest.raises(ValueError):
        GamepadFrame(buttons=frozenset({"TURBO"}))


def test_packet_roundtrip():
    p = IntentPacket(seq=1, source=Source.REFLEX, created_at=5.0, ttl_ms=100,
                     frames=(GamepadFrame(lx=0.5, buttons=frozenset({"SOUTH"})),), delegation_id="d")
    assert IntentPacket.from_dict(json.loads(json.dumps(p.to_dict()))) == p


def test_signature_rejects_tampering_and_wrong_key():
    raw = sign_message(KEY, "intent", {"a": 1})
    assert verify_message(KEY, raw) == ("intent", {"a": 1})
    tampered = raw.replace(b'"a":1', b'"a":2')
    with pytest.raises(BadSignature):
        verify_message(KEY, tampered)
    with pytest.raises(BadSignature):
        verify_message(b"x" * 32, raw)
    with pytest.raises(BadSignature):
        verify_message(KEY, b"not json")


def _write_log(path, n=5):
    log = IntentLog(path)
    for i in range(n):
        log.append("test", i=i)
    log.close(seal_key=KEY)


def test_log_chain_verifies(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_log(p)
    ok, n, _, problem = verify_log(p)
    assert ok and n == 5 and problem == ""
    assert verify_seal(p, KEY) == (True, "")


def test_log_detects_edit(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_log(p)
    lines = p.read_text().splitlines()
    lines[2] = lines[2].replace('"i":2', '"i":99')
    p.write_text("\n".join(lines) + "\n")
    ok, _, _, problem = verify_log(p)
    assert not ok and "hash mismatch" in problem


def test_log_detects_deleted_line(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_log(p)
    lines = p.read_text().splitlines()
    del lines[1]
    p.write_text("\n".join(lines) + "\n")
    assert not verify_log(p)[0]


def test_truncation_passes_chain_but_fails_seal(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_log(p)
    lines = p.read_text().splitlines()
    p.write_text("\n".join(lines[:3]) + "\n")
    assert verify_log(p)[0]                      # the chain alone cannot see truncation
    ok, problem = verify_seal(p, KEY)
    assert not ok and "truncated" in problem


def test_half_written_last_line_is_reported(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_log(p)
    with p.open("a") as fh:
        fh.write('{"prev": "abc", "hash"')
    ok, _, _, problem = verify_log(p)
    assert not ok and "unreadable" in problem


def test_seal_with_wrong_key_fails(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_log(p)
    assert verify_seal(p, b"z" * 32) == (False, "seal signature mismatch")


def test_reopen_continues_chain_and_refuses_broken_log(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_log(p, 3)
    log = IntentLog(p)
    log.append("more")
    log.close()
    ok, n, _, _ = verify_log(p)
    assert ok and n == 4
    p.write_text(p.read_text().replace('"kind":"more"', '"kind":"edited"'))
    with pytest.raises(RuntimeError):
        IntentLog(p)
