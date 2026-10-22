import pytest

from conftest import FakeClock
from powder_ranger.governor.governor import Governor
from powder_ranger.governor.intent_log import IntentLog
from powder_ranger.governor.policy import GovernorConfig
from powder_ranger.governor.safety import KillSwitch
from powder_ranger.intent import Delegation, GamepadFrame, IntentPacket, Source
from powder_ranger.motor.model import MotorModel, MotorProfile
from powder_ranger.output.adapters import DryRunAdapter

FAST = MotorProfile(reaction_min_ms=0, reaction_max_ms=1, tremor_amp=0, drift_sigma=0)


@pytest.fixture
def rig(tmp_path):
    c = FakeClock()
    a = DryRunAdapter()
    kill = KillSwitch()
    g = Governor(GovernorConfig(claim_ttl_ms=250), MotorModel(FAST, seed=1), a, IntentLog(tmp_path / "s.jsonl"),
                 kill, lambda: True, clock=c)
    g.handle("grant", Delegation(id="d", scope="full_autopilot", granted_at=c()).to_dict())
    seq = {"n": 0}

    def send(source, frame, claims=(), deleg=None):
        seq["n"] += 1
        g.handle("intent", IntentPacket(seq=seq["n"], source=source, created_at=c(), ttl_ms=250, frames=(frame,),
                                        delegation_id=deleg, claims=claims, producer=source.value).to_dict())

    def run(n):
        for _ in range(n):
            c.advance(1 / 120)
            g.tick()
        return a.frames[-1]
    return g, c, kill, send, run


def test_gaze_steers_while_companion_keeps_throttle(rig):
    g, c, kill, send, run = rig
    send(Source.REFLEX, GamepadFrame(lx=1.0, rt=1.0), deleg="d")
    assert run(40).lx > 0.9
    for _ in range(10):                                   # player looks left, continuously
        send(Source.PLAYER, GamepadFrame(lx=-0.7), claims=("lx",))
        send(Source.REFLEX, GamepadFrame(lx=1.0, rt=1.0), deleg="d")   # companion still allowed
        f = run(3)
    assert f.lx == -0.7 and f.rt > 0.9                    # player steering, companion throttle
    assert g.stats["denied"] == 0


def test_partial_claim_expires_and_companion_resumes(rig):
    g, c, kill, send, run = rig
    send(Source.REFLEX, GamepadFrame(lx=1.0), deleg="d")
    run(30)
    send(Source.PLAYER, GamepadFrame(lx=-0.5), claims=("lx",))
    assert run(1).lx == -0.5
    send(Source.REFLEX, GamepadFrame(lx=1.0), deleg="d")
    assert run(40).lx > 0.9                               # 330 ms later: claim expired


def test_full_takeover_still_blocks_companion_and_clears_claims(rig):
    g, c, kill, send, run = rig
    send(Source.PLAYER, GamepadFrame(lx=-0.5), claims=("lx",))
    send(Source.PLAYER, GamepadFrame(ly=1.0))             # no claims = whole pad
    send(Source.REFLEX, GamepadFrame(lx=1.0), deleg="d")
    f = run(5)
    assert f.ly == 1.0 and f.lx == 0.0 and g.stats["denied"] == 1


def test_kill_switch_drops_claims(rig):
    g, c, kill, send, run = rig
    send(Source.PLAYER, GamepadFrame(lx=-0.5), claims=("lx",))
    kill.trip("test")
    assert run(2) == GamepadFrame()


def test_only_player_packets_may_claim():
    with pytest.raises(ValueError):
        IntentPacket(seq=1, source=Source.REFLEX, created_at=0, ttl_ms=1, frames=(GamepadFrame(),), claims=("lx",))
    with pytest.raises(ValueError):
        IntentPacket(seq=1, source=Source.PLAYER, created_at=0, ttl_ms=1, frames=(GamepadFrame(),), claims=("turbo",))


def test_player_loop_forwards_gaze_claims():
    from powder_ranger.inputs.player import PlayerInputLoop

    class Src:
        name = "gaze"
        def read(self): return GamepadFrame(lx=0.6)
        def claims(self, f): return ("lx",)
    sent = []
    PlayerInputLoop(Src(), lambda f, claims=(): sent.append(claims), clock=FakeClock()).poll()
    assert sent == [("lx",)]
