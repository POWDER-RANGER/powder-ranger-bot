import pytest
from conftest import FakeClock

from powder_ranger.governor.governor import Governor
from powder_ranger.governor.intent_log import IntentLog
from powder_ranger.governor.policy import GovernorConfig
from powder_ranger.governor.safety import KillSwitch
from powder_ranger.inputs.player import (
    VK_NAMES,
    FakeSource,
    KeyboardSource,
    PlayerInputLoop,
    pick_player_slot,
    xinput_state_to_frame,
)
from powder_ranger.intent import Delegation, GamepadFrame, IntentPacket, Source
from powder_ranger.motor.model import MotorModel, MotorProfile
from powder_ranger.output.adapters import DryRunAdapter


def test_xinput_conversion_deadzones_and_buttons():
    f = xinput_state_to_frame(0x1000 | 0x0001, lt=255, rt=10, lx=32767, ly=0, rx=5000, ry=5000)
    assert f.buttons == frozenset({"SOUTH", "DPAD_UP"})
    assert f.lx == 1.0 and f.ly == 0.0
    assert f.rx == 0.0 and f.ry == 0.0          # inside right dead zone
    assert f.lt == 1.0 and f.rt == 0.0          # below trigger threshold
    up = xinput_state_to_frame(0, 0, 0, 0, 32767, 0, 0)
    assert up.ly == 1.0                          # XInput +y is up, same as GamepadFrame


def test_slot_must_be_unambiguous():
    assert pick_player_slot([1]) == 1
    with pytest.raises(RuntimeError):
        pick_player_slot([])
    with pytest.raises(RuntimeError):
        pick_player_slot([0, 1])


def test_keyboard_mapping():
    down = {VK_NAMES["W"], VK_NAMES["D"], VK_NAMES["SPACE"]}
    kb = KeyboardSource({"W": "LY+", "D": "LX+", "A": "LX-", "SPACE": "SOUTH"}, key_state=lambda vk: vk in down)
    f = kb.read()
    assert (f.lx, f.ly) == (1.0, 1.0) and f.buttons == frozenset({"SOUTH"})
    with pytest.raises(ValueError):
        KeyboardSource({"W": "TURBO"}, key_state=lambda vk: False)
    with pytest.raises(ValueError):
        KeyboardSource({"NOTAKEY": "SOUTH"}, key_state=lambda vk: False)


def test_loop_sends_while_active_then_one_neutral_then_quiet():
    sent, presence = [], []
    frames = [GamepadFrame(), GamepadFrame(lx=0.5), GamepadFrame(lx=0.6), GamepadFrame(), GamepadFrame()]
    loop = PlayerInputLoop(FakeSource(frames), sent.append, presence=presence.append, clock=FakeClock())
    for _ in frames:
        loop.poll()
    assert [f.lx for f in sent] == [0.5, 0.6, 0.0]
    assert presence == ["fake"]


def test_unplug_releases_held_input():
    sent = []
    loop = PlayerInputLoop(FakeSource([GamepadFrame(buttons=frozenset({"SOUTH"})), None, None]),
                           sent.append, clock=FakeClock())
    for _ in range(3):
        loop.poll()
    assert sent[-1] == GamepadFrame() and loop.lost and len(sent) == 2


def test_steady_filter_smooths_player_tremor():
    import math
    c = FakeClock(0.0)
    frames = [GamepadFrame(lx=0.5 + 0.1 * math.sin(2 * math.pi * 6 * i / 120)) for i in range(240)]
    PlayerInputLoop(FakeSource(list(frames)), lambda f: None, clock=c)
    sent = []
    steady = PlayerInputLoop(FakeSource(list(frames)), sent.append, steady=True, clock=c)
    for _ in frames:
        steady.poll()
        c.advance(1 / 120)
    tail = [f.lx for f in sent[-120:]]
    assert max(tail) - min(tail) < 0.2 / 3              # raw spread is 0.2


def test_player_input_takes_over_from_companion_through_governor(tmp_path):
    c = FakeClock()
    adapter = DryRunAdapter()
    gov = Governor(GovernorConfig(player_override_hold_ms=1000),
                   MotorModel(MotorProfile(reaction_min_ms=0, reaction_max_ms=1, tremor_amp=0, drift_sigma=0)),
                   adapter, IntentLog(tmp_path / "s.jsonl"), KillSwitch(), lambda: True, clock=c)
    gov.handle("grant", Delegation(id="d", scope="full_autopilot", granted_at=c()).to_dict())
    seq = iter(range(1, 10000))

    def companion():
        gov.handle("intent", IntentPacket(seq=next(seq), source=Source.REFLEX, created_at=c(), ttl_ms=250,
                                          frames=(GamepadFrame(lx=1.0),), delegation_id="d").to_dict())

    pseq = iter(range(1, 10000))

    def player_send(f):
        gov.handle("intent", IntentPacket(seq=next(pseq), source=Source.PLAYER, created_at=c(), ttl_ms=150,
                                          frames=(f,)).to_dict())

    companion()
    for _ in range(30):
        c.advance(1 / 120); gov.tick()
    assert adapter.frames[-1].lx > 0.9                       # companion driving right

    loop = PlayerInputLoop(FakeSource([GamepadFrame(lx=-1.0)] * 30 + [GamepadFrame()]), player_send, clock=c)
    for _ in range(31):
        companion()                                           # companion keeps trying
        loop.poll()
        c.advance(1 / 120); gov.tick()
    assert any(f.lx == -1.0 for f in adapter.frames[-31:])    # player's left won
    companion()
    c.advance(1 / 120); gov.tick()
    assert adapter.frames[-1].lx == 0.0                       # held off right after release
    c.advance(1.1)
    companion()
    for _ in range(30):
        c.advance(1 / 120); gov.tick()
    assert adapter.frames[-1].lx > 0.9                        # companion resumes after the hold
