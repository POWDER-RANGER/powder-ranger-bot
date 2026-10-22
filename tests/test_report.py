from conftest import FakeClock
from powder_ranger.governor.governor import Governor
from powder_ranger.governor.intent_log import IntentLog
from powder_ranger.governor.policy import GovernorConfig
from powder_ranger.governor.safety import KillSwitch
from powder_ranger.intent import Delegation, GamepadFrame, IntentPacket, Source
from powder_ranger.motor.model import MotorModel
from powder_ranger.output.adapters import DryRunAdapter
from powder_ranger.report import build_report, format_report

KEY = b"r" * 32


def test_report_counts_decisions_authorship_and_safety(tmp_path):
    c = FakeClock()
    log = tmp_path / "session-x.jsonl"
    kill = KillSwitch()
    gov = Governor(GovernorConfig(), MotorModel(), DryRunAdapter(), IntentLog(log), kill, lambda: True,
                   clock=c, seal_key=KEY, session_info={"pack_id": "supertuxkart"})
    gov.handle("command", {"id": "c1", "verb": "delegate", "via": "voice"})
    gov.handle("grant", Delegation(id="d", scope="full_autopilot", granted_at=c()).to_dict())
    pk = lambda seq, src, deleg=None: IntentPacket(seq=seq, source=src, created_at=c() - 0.01, ttl_ms=250,
                                                   frames=(GamepadFrame(lx=0.5),), delegation_id=deleg).to_dict()
    for i in range(1, 4):
        gov.handle("intent", pk(i, Source.REFLEX, "d"))
        c.advance(0.2)
    gov.handle("intent", pk(10, Source.PLAYER))
    gov.handle("intent", pk(11, Source.REFLEX, "d"))          # denied: player override
    gov.handle("intent", pk(12, Source.REFLEX, None))         # denied: no delegation
    kill.trip("voice: stop")
    gov.close()

    r = build_report(log, seal_key=KEY)
    assert r["integrity"]["chain_ok"] and r["integrity"]["seal_ok"]
    assert r["decisions"]["allowed"] == 4 and r["decisions"]["denied"] == 2
    assert r["decisions"]["allowed_by_source"] == {"reflex": 3, "player": 1}
    assert r["authorship"]["player_share_of_allowed_output"] == 0.25
    assert r["authorship"]["player_commands"] == ["delegate"]
    assert r["safety"]["kill_switch"] == ["voice: stop"]
    assert r["latency_ms"]["packet_age_at_governor"]["p50"] == 10.0
    assert r["session"]["pack_id"] == "supertuxkart"
    text = format_report(r)
    assert "player share of output 25%" in text and "player override" in text
