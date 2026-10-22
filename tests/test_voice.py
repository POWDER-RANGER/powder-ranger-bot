import pytest

from conftest import FakeClock
from powder_ranger.governor.governor import Governor
from powder_ranger.governor.intent_log import IntentLog
from powder_ranger.governor.policy import GovernorConfig, GovernorPolicy
from powder_ranger.governor.safety import KillSwitch
from powder_ranger.inputs.commands import parse
from powder_ranger.inputs.voice import VoiceDispatcher
from powder_ranger.intent import GamepadFrame, IntentPacket, Source
from powder_ranger.motor.model import MotorModel
from powder_ranger.output.adapters import DryRunAdapter


@pytest.mark.parametrize("text", ["stop", "Stop!", "STOP the car", "okay halt", "freeze", "abort now"])
def test_stop_words(text):
    assert parse(text).verb == "stop"


@pytest.mark.parametrize("text", ["don't stop", "do not stop", "never stop", "nonstop", "stopwatch", "unstoppable"])
def test_not_stop(text):
    c = parse(text)
    assert c is None or c.verb != "stop"


def test_negated_resume_means_hold():
    assert parse("don't keep going").verb == "hold"


@pytest.mark.parametrize("text,verb,scope", [
    ("you play", "delegate", "full_autopilot"), ("take over please", "delegate", "full_autopilot"),
    ("you drive", "delegate", "driving"), ("my turn", "revoke", None), ("I've got it", "revoke", None),
    ("let me play", "revoke", None), ("resume", "resume", None),
])
def test_control_phrases(text, verb, scope):
    c = parse(text)
    assert c.verb == verb and c.scope == scope


def test_movement_grammar():
    c = parse("move to the tower silently")
    assert (c.verb, c.target, c.manner) == ("move", "tower", "silent")
    c = parse("go to the north gate")
    assert (c.verb, c.target, c.manner) == ("move", "north gate", None)
    assert parse("go loud").verb == "set_style" and parse("go loud").manner == "loud"
    assert parse("flank left").target == "left"


def test_gibberish_is_ignored():
    assert parse("") is None and parse("banana sandwich") is None


class Rec:
    def __init__(self):
        self.msgs, self.taps, self.said = [], [], []


def disp(r):
    return VoiceDispatcher(lambda t, b: r.msgs.append((t, b)), r.taps.append, r.said.append, clock=FakeClock())


def test_dispatch_stop_halts_and_logs_command():
    r = Rec()
    disp(r).handle_text("stop")
    kinds = [t for t, _ in r.msgs]
    assert kinds == ["presence", "command", "halt"] and r.said == ["Stopped."]


def test_dispatch_delegate_and_revoke():
    r = Rec()
    d = disp(r)
    d.handle_text("you play")
    grant = [b for t, b in r.msgs if t == "grant"][0]
    assert grant["scope"] == "full_autopilot" and d.active_delegation == grant["id"]
    d.handle_text("my turn")
    assert ("revoke", {"id": None}) in r.msgs and d.active_delegation is None


def test_dispatch_unbuilt_commands_answer_honestly():
    r = Rec()
    disp(r).handle_text("move to the tower silently")
    assert r.said == ["I heard you, but I can't do that yet."]
    assert [t for t, _ in r.msgs] == ["presence", "command"]


def test_dispatch_jump_is_one_packet_press_then_release():
    r = Rec()
    disp(r).handle_text("jump")
    assert r.taps == [[GamepadFrame(buttons=frozenset({"SOUTH"})), GamepadFrame()]]


def test_two_player_producers_do_not_reject_each_other():
    """Regression: player pad and voice both send as PLAYER with independent sequence numbers."""
    p = GovernorPolicy(GovernorConfig())
    mk = lambda seq, prod: IntentPacket(seq=seq, source=Source.PLAYER, created_at=1.0, ttl_ms=100,
                                        frames=(GamepadFrame(),), producer=prod)
    assert p.evaluate(mk(5000, "voice"), 1.0, True).allow
    assert p.evaluate(mk(1200, "pad"), 1.0, True).allow          # lower seq, different producer
    assert not p.evaluate(mk(1200, "pad"), 1.0, True).allow      # same producer replay still caught


def test_voice_stop_through_governor_releases_controls(tmp_path):
    c = FakeClock()
    adapter = DryRunAdapter()
    gov = Governor(GovernorConfig(), MotorModel(), adapter, IntentLog(tmp_path / "s.jsonl"),
                   KillSwitch(), lambda: True, clock=c)
    d = VoiceDispatcher(gov.handle, lambda fs: None, lambda s: None, clock=c)
    gov.handle("intent", IntentPacket(seq=1, source=Source.PLAYER, created_at=c(), ttl_ms=100,
                                      frames=(GamepadFrame(buttons=frozenset({"SOUTH"})),)).to_dict())
    gov.tick()
    assert "SOUTH" in adapter.frames[-1].buttons
    d.handle_text("stop")
    assert adapter.frames[-1] == GamepadFrame() and gov.policy.halted
