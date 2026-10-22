"""Regressions for defects found in the October 2026 code review (docs/REVIEW-2026-10.md).

F1/F2  motor scheduling discarded chunks and held stale values; watchdog watched packets, not output
F3     malformed or non-finite packets ended the session
F5     voice/launcher grants ignored the game pack's allowed scopes
F6     kill-switch ordering: halt must be latched before the neutral frame is written
F7     the STOP file must not depend on the working directory
"""

import json

import pytest

from conftest import FakeClock
from powder_ranger.config import load_settings
from powder_ranger.governor.governor import Governor
from powder_ranger.governor.intent_log import IntentLog
from powder_ranger.governor.policy import GovernorConfig
from powder_ranger.governor.safety import KillSwitch
from powder_ranger.intent import Delegation, GamepadFrame, IntentPacket, Source, sign_message
from powder_ranger.motor.model import MotorModel, MotorProfile
from powder_ranger.output.adapters import DryRunAdapter

KEY = b"r" * 32


def make(tmp_path, clock, profile=None, adapter=None, **cfg):
    adapter = adapter or DryRunAdapter(keep=1)
    kill = KillSwitch(tmp_path / "STOP")
    gov = Governor(GovernorConfig(**cfg), MotorModel(profile or MotorProfile(), seed=1), adapter,
                   IntentLog(tmp_path / "s.jsonl"), kill, lambda: True, clock=clock, seal_key=KEY)
    return gov, adapter, kill


def grant(gov, clock, scope="full_autopilot"):
    gov.handle("grant", Delegation(id="d1", scope=scope, granted_at=clock()).to_dict())


def chunk(seq, clock, lx, n=16, dt=1000 / 60):
    return IntentPacket(seq=seq, source=Source.REFLEX, created_at=clock(), ttl_ms=400,
                        frames=tuple(GamepadFrame(lx=lx) for _ in range(n)), frame_dt_ms=dt,
                        delegation_id="d1", producer="p").to_dict()


def drive(gov, clock, seconds, send_every=None, lx=0.8, first_seq=1, tick=1 / 120):
    """Run the loop; send a chunk every `send_every` seconds. Returns [(t, lx)]."""
    out, seq, nxt, t0 = [], first_seq, clock(), clock()
    while clock() - t0 < seconds:
        if send_every is not None and clock() >= nxt:
            gov.handle("intent", chunk(seq, clock, lx(clock() - t0) if callable(lx) else lx))
            seq += 1
            nxt += send_every
        clock.advance(tick)
        out.append((clock() - t0, gov.tick().lx))
    return out


# --------------------------------------------------------------------------- F1 / F2

@pytest.mark.parametrize("interval", [0.05, 0.10, 0.15, 0.20, 0.30])
def test_fast_packet_stream_is_not_starved_by_reaction_delay(tmp_path, interval):
    """Packets arriving faster than the reaction delay used to erase each other: nothing played."""
    c = FakeClock()
    gov, _, _ = make(tmp_path, c)
    grant(gov, c)
    out = drive(gov, c, 4.0, send_every=interval)
    onset = next(t for t, v in out if v > 0.4)
    assert onset < 0.7                                        # one reaction delay, once
    tail = [v for t, v in out if t > 1.5]
    assert min(tail) > 0.6                                    # and then it stays on


def test_reaction_delay_still_applies_at_onset(tmp_path):
    c = FakeClock()
    gov, _, _ = make(tmp_path, c)
    grant(gov, c)
    out = drive(gov, c, 1.0, send_every=0.1)
    first_move = next(t for t, v in out if v > 0.05)
    assert first_move >= 0.12                                 # reaction_min_ms: humanization kept


def test_newest_command_wins_instead_of_a_stale_value_being_held(tmp_path):
    c = FakeClock()
    gov, _, _ = make(tmp_path, c)
    grant(gov, c)
    out = drive(gov, c, 3.4, send_every=0.1, lx=lambda t: 0.8 if t < 0.4 else -0.8)
    assert all(v < -0.5 for t, v in out if t > 1.6)
    assert not gov._watchdog_neutral


def test_watchdog_measures_played_output_not_packet_arrival(tmp_path):
    """Packets that never produce a frame (empty chunks) must not keep a held value alive."""
    c = FakeClock()
    gov, _, _ = make(tmp_path, c, watchdog_ms=500)
    grant(gov, c)
    drive(gov, c, 1.0, send_every=0.1)                        # real output, held at 0.8
    seq = 1000
    t0 = c()
    last = 0.8
    while c() - t0 < 1.5:
        if int((c() - t0) * 10) != int((c() - t0 - 1 / 120) * 10):
            gov.handle("intent", IntentPacket(seq=seq, source=Source.REFLEX, created_at=c(), ttl_ms=400,
                                              frames=(), delegation_id="d1", producer="p").to_dict())
            seq += 1
        c.advance(1 / 120)
        last = gov.tick().lx
    assert abs(last) < 0.05


def test_long_chunk_still_plays_out_with_continuity(tmp_path):
    c = FakeClock()
    gov, _, _ = make(tmp_path, c, watchdog_ms=500)
    grant(gov, c)
    gov.handle("intent", chunk(1, c, 0.7, n=16, dt=100.0))     # 1.5 s long
    out = drive(gov, c, 1.5, first_seq=2)
    assert not gov._watchdog_neutral
    assert max(v for t, v in out if t > 1.0) > 0.6


# --------------------------------------------------------------------------- F3

BAD_BODIES = {
    "missing fields": {"seq": 1},
    "unknown button": {"seq": 1, "source": "reflex", "created_at": 0.0, "ttl_ms": 100,
                       "frames": [{"buttons": ["TRIANGLE"]}]},
    "nan stick": {"seq": 1, "source": "reflex", "created_at": 0.0, "ttl_ms": 100,
                  "frames": [{"lx": float("nan")}]},
    "inf stick": {"seq": 1, "source": "reflex", "created_at": 0.0, "ttl_ms": 100,
                  "frames": [{"ly": float("inf")}]},
    "nan timestamp": {"seq": 1, "source": "reflex", "created_at": float("nan"), "ttl_ms": 100, "frames": []},
    "zero frame spacing": {"seq": 1, "source": "reflex", "created_at": 0.0, "ttl_ms": 100,
                           "frames": [{}], "frame_dt_ms": 0},
    "frames not a list": {"seq": 1, "source": "reflex", "created_at": 0.0, "ttl_ms": 100, "frames": 5},
    "huge chunk": {"seq": 1, "source": "reflex", "created_at": 0.0, "ttl_ms": 100, "frames": [{}] * 5000},
}


@pytest.mark.parametrize("name", sorted(BAD_BODIES))
def test_malformed_packet_is_rejected_logged_and_the_session_continues(tmp_path, name):
    c = FakeClock()
    gov, adapter, _ = make(tmp_path, c)
    grant(gov, c)
    gov.handle_raw(KEY, sign_message(KEY, "intent", BAD_BODIES[name]))      # must not raise
    assert gov.stats["malformed"] == 1
    gov.handle("intent", chunk(2, c, 0.8))
    out = drive(gov, c, 1.0, first_seq=3)
    assert out[-1][1] > 0.5                                    # the Governor is still serving
    gov.close()
    kinds = [json.loads(line)["record"]["kind"] for line in (tmp_path / "s.jsonl").read_text().splitlines()]
    assert "rejected_message" in kinds


def test_malformed_grant_is_rejected_not_fatal(tmp_path):
    c = FakeClock()
    gov, _, _ = make(tmp_path, c)
    gov.handle_raw(KEY, sign_message(KEY, "grant", {"id": "x"}))           # missing scope
    assert gov.stats["malformed"] == 1 and not gov.policy.delegations


def test_gamepad_frame_rejects_non_finite_values():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            GamepadFrame(lx=bad)
        with pytest.raises(ValueError):
            GamepadFrame(rt=bad)
    assert GamepadFrame(lx=5.0).lx == 1.0                      # ordinary out-of-range still clamps


# --------------------------------------------------------------------------- F5

def test_grant_outside_the_packs_scopes_is_refused(tmp_path):
    c = FakeClock()
    gov, _, _ = make(tmp_path, c, allowed_scopes=("driving",))
    grant(gov, c, scope="full_autopilot")
    assert not gov.policy.delegations
    gov.handle("grant", Delegation(id="d2", scope="driving", granted_at=c()).to_dict())
    assert "d2" in gov.policy.delegations


def test_no_scope_limit_when_none_configured(tmp_path):
    c = FakeClock()
    gov, _, _ = make(tmp_path, c)
    grant(gov, c, scope="routine")
    assert "d1" in gov.policy.delegations


# --------------------------------------------------------------------------- F6

class OrderCheckingAdapter(DryRunAdapter):
    def __init__(self):
        super().__init__(keep=10)
        self.halted_when_neutral_written = []
        self.gov = None

    def apply(self, frame):
        if self.gov is not None and frame == GamepadFrame():
            self.halted_when_neutral_written.append(self.gov.policy.halted)
        super().apply(frame)


def test_halt_is_latched_before_neutral_is_written_on_trip(tmp_path):
    c = FakeClock()
    adapter = OrderCheckingAdapter()
    gov, _, kill = make(tmp_path, c, adapter=adapter)
    adapter.gov = gov
    grant(gov, c)
    kill.trip("test")
    assert adapter.halted_when_neutral_written and adapter.halted_when_neutral_written[0] is True


# --------------------------------------------------------------------------- F7

def test_default_stop_file_is_absolute_and_independent_of_cwd(tmp_path, monkeypatch):
    s1 = load_settings()
    monkeypatch.chdir(tmp_path)
    s2 = load_settings()
    assert s1.stop_file == s2.stop_file
    assert __import__("pathlib").Path(s1.stop_file).is_absolute()
