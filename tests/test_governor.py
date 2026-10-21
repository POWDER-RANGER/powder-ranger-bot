import json
import threading
import time

import numpy as np

from conftest import FakeClock
from powder_ranger.config import load_settings, validate_settings, ROOT
from powder_ranger.governor.client import GovernorClient
from powder_ranger.governor.governor import Governor
from powder_ranger.governor.intent_log import IntentLog, verify_log, verify_seal
from powder_ranger.governor.policy import GovernorConfig
from powder_ranger.governor.safety import KillSwitch
from powder_ranger.intent import Delegation, GamepadFrame, IntentPacket, Source, sign_message
from powder_ranger.motor.model import MotorModel, MotorProfile
from powder_ranger.output.adapters import DryRunAdapter
from powder_ranger.runners import nitrogen

KEY = b"s" * 32
FAST = MotorProfile(reaction_min_ms=0, reaction_max_ms=1, tremor_amp=0, drift_sigma=0)


def make_gov(tmp_path, clock, focused=True, **cfg):
    adapter = DryRunAdapter()
    kill = KillSwitch(tmp_path / "STOP")
    gov = Governor(GovernorConfig(**cfg), MotorModel(FAST, seed=1), adapter,
                   IntentLog(tmp_path / "s.jsonl"), kill, lambda: focused, clock=clock, seal_key=KEY)
    return gov, adapter, kill


def intent(seq, clock, source=Source.REFLEX, deleg="d1", frame=None):
    return IntentPacket(seq=seq, source=source, created_at=clock(), ttl_ms=250,
                        frames=(frame or GamepadFrame(lx=1.0, buttons=frozenset({"SOUTH"})),),
                        delegation_id=deleg).to_dict()


def grant(gov, clock, scope="full_autopilot"):
    gov.handle("grant", Delegation(id="d1", scope=scope, granted_at=clock()).to_dict())


def ticks(gov, clock, n):
    out = []
    for _ in range(n):
        clock.advance(1 / 120)
        out.append(gov.tick())
    return out


def test_delegated_intent_reaches_output(tmp_path):
    c = FakeClock()
    gov, adapter, _ = make_gov(tmp_path, c)
    grant(gov, c)
    gov.handle("intent", intent(1, c))
    frames = ticks(gov, c, 30)
    assert frames[-1].lx > 0.9 and "SOUTH" in frames[-1].buttons


def test_undelegated_intent_never_reaches_output(tmp_path):
    c = FakeClock()
    gov, adapter, _ = make_gov(tmp_path, c)
    gov.handle("intent", intent(1, c))
    assert all(f == GamepadFrame() for f in ticks(gov, c, 30))
    assert gov.stats["denied"] == 1


def test_kill_switch_releases_held_controls_immediately(tmp_path):
    c = FakeClock()
    gov, adapter, kill = make_gov(tmp_path, c)
    grant(gov, c)
    gov.handle("intent", intent(1, c))
    assert "SOUTH" in ticks(gov, c, 20)[-1].buttons
    kill.trip("test")                                   # e.g. from the hotkey thread
    assert adapter.frames[-1] == GamepadFrame()          # neutral written before anything else
    gov.handle("intent", intent(2, c))
    assert all(f == GamepadFrame() for f in ticks(gov, c, 20))


def test_stop_file_trips_and_resume_needs_new_grant(tmp_path):
    c = FakeClock()
    gov, adapter, kill = make_gov(tmp_path, c)
    grant(gov, c)
    (tmp_path / "STOP").touch()
    ticks(gov, c, 1)
    assert kill.tripped and gov.policy.halted
    (tmp_path / "STOP").unlink()
    gov.handle("resume", {})
    gov.handle("intent", intent(2, c))
    assert all(f == GamepadFrame() for f in ticks(gov, c, 20))   # delegation was revoked by the trip
    grant(gov, c)
    gov.handle("intent", intent(3, c))
    assert ticks(gov, c, 30)[-1].lx > 0.9


def test_watchdog_eases_to_neutral_when_policy_stalls(tmp_path):
    c = FakeClock()
    gov, adapter, _ = make_gov(tmp_path, c, watchdog_ms=500)
    grant(gov, c)
    gov.handle("intent", intent(1, c))
    ticks(gov, c, 30)
    last = ticks(gov, c, 200)[-1]                       # 1.7 s with no new intent
    assert abs(last.lx) < 0.01 and not last.buttons


def test_focus_loss_blocks_companion_but_not_player(tmp_path):
    c = FakeClock()
    gov, adapter, _ = make_gov(tmp_path, c, focused=False)
    grant(gov, c)
    gov.handle("intent", intent(1, c))
    assert ticks(gov, c, 30)[-1] == GamepadFrame()
    gov.handle("intent", intent(1, c, source=Source.PLAYER, deleg=None, frame=GamepadFrame(ly=1.0)))
    assert ticks(gov, c, 5)[-1].ly == 1.0


def test_bad_signature_rejected_and_logged(tmp_path):
    c = FakeClock()
    gov, adapter, _ = make_gov(tmp_path, c)
    gov.handle_raw(KEY, sign_message(b"w" * 32, "grant", {"id": "x"}))
    assert gov.stats["bad_signature"] == 1 and not gov.policy.delegations


def test_close_neutralizes_and_seals_even_if_adapter_fails(tmp_path):
    c = FakeClock()

    class Broken(DryRunAdapter):
        def close(self):
            raise RuntimeError("driver gone")

    kill = KillSwitch()
    log = IntentLog(tmp_path / "s.jsonl")
    adapter = Broken()
    gov = Governor(GovernorConfig(), MotorModel(FAST), adapter, log, kill, lambda: True, clock=c, seal_key=KEY)
    try:
        gov.close()
    except RuntimeError:
        pass
    assert adapter.frames[-1] == GamepadFrame()
    assert verify_seal(tmp_path / "s.jsonl", KEY) == (True, "")


def test_every_allowed_output_is_attributed_in_the_log(tmp_path):
    c = FakeClock()
    gov, _, _ = make_gov(tmp_path, c)
    grant(gov, c)
    for i in range(1, 6):
        gov.handle("intent", intent(i, c))
        ticks(gov, c, 3)
    gov.close()
    ok, n, _, _ = verify_log(tmp_path / "s.jsonl")
    assert ok
    records = [json.loads(l)["record"] for l in (tmp_path / "s.jsonl").read_text().splitlines()]
    allowed = [r for r in records if r["kind"] == "intent" and r["allow"]]
    assert allowed and all(r["delegation_id"] == "d1" for r in allowed)


# --------------------------------------------------------------------------
# configuration: development vs deployment
# --------------------------------------------------------------------------

def test_default_settings_are_valid_deployment():
    s = load_settings()
    assert s.mode == "deployment" and validate_settings(s) == []


def test_development_profile_is_valid_but_refused_online(tmp_path):
    dev = ROOT / "config" / "profiles" / "development.yaml"
    s = load_settings(profile_path=dev)
    assert s.mode == "development" and validate_settings(s) == []
    s.governor.online_mode = True
    assert any("isolated" in p for p in validate_settings(s))


def test_dev_settings_cannot_leak_into_deployment(tmp_path):
    prof = tmp_path / "sneaky.yaml"
    prof.write_text("motor:\n  humanize: false\n  max_presses_per_sec: 40\n")
    s = load_settings(profile_path=prof)              # mode stays deployment
    problems = validate_settings(s)
    assert any("humanize" in p for p in problems) and any("max_presses_per_sec" in p for p in problems)


# --------------------------------------------------------------------------
# headless pipeline: fake NitroGen + fake capture -> real ZMQ -> Governor
# --------------------------------------------------------------------------

def test_prediction_conversion():
    tokens = nitrogen.NITROGEN_TOKENS
    b = np.zeros((2, len(tokens)))
    b[0, tokens.index("SOUTH")] = 0.9
    b[0, tokens.index("START")] = 0.9
    b[0, tokens.index("RIGHT_UP")] = 0.9                # ignored token
    b[1, tokens.index("LEFT_TRIGGER")] = 0.7
    frames = nitrogen.prediction_to_frames({"j_left": [[0.5, 0.25], [0, -1]],
                                            "j_right": [[0, 0], [0, 0]], "buttons": b})
    assert frames[0].lx == 0.5 and frames[0].ly == -0.25          # NitroGen +y down -> +y up
    assert frames[0].buttons == frozenset({"SOUTH", "START"})
    assert frames[1].ly == 1.0 and abs(frames[1].lt - 0.7) < 1e-9 and not frames[1].buttons


def test_headless_pipeline_end_to_end(tmp_path):
    endpoint = "tcp://127.0.0.1:5591"
    adapter = DryRunAdapter()
    kill = KillSwitch()
    gov = Governor(GovernorConfig(), MotorModel(FAST, seed=1), adapter,
                   IntentLog(tmp_path / "s.jsonl"), kill, lambda: True, seal_key=KEY)
    t = threading.Thread(target=gov.serve, args=(endpoint, KEY), kwargs={"tick_hz": 240}, daemon=True)
    t.start()
    time.sleep(0.2)

    class FakeServer:
        def reset(self): pass
        def info(self): return {"action_downsample_ratio": 1, "ckpt_path": "fake.pt"}
        def predict(self, img):
            assert img.size == (256, 256)
            b = np.zeros((4, len(nitrogen.NITROGEN_TOKENS)))
            b[:, nitrogen.NITROGEN_TOKENS.index("SOUTH")] = 1.0
            return {"j_left": [[0.8, 0.0]] * 4, "j_right": [[0, 0]] * 4, "buttons": b}

    class FakeCapture:
        def grab(self): return np.full((480, 640, 3), 128, dtype=np.uint8)
        def close(self): pass

    control = GovernorClient(endpoint, KEY, Source.SYSTEM)
    control.grant(Delegation(id="d1", scope="full_autopilot", granted_at=time.monotonic()))
    time.sleep(0.1)
    reflex = GovernorClient(endpoint, KEY, Source.REFLEX)
    sent = nitrogen.run(reflex, "fake.exe", "d1", max_steps=5, capture=FakeCapture(), server=FakeServer(),
                        metrics_path=tmp_path / "m.csv")
    time.sleep(0.6)
    assert sent == 5
    assert any(f.lx > 0.5 and "SOUTH" in f.buttons for f in adapter.frames)

    control.halt("test halt")
    time.sleep(0.1)
    assert adapter.frames[-1] == GamepadFrame()
    control.shutdown()
    t.join(timeout=2)
    assert not t.is_alive()
    assert verify_seal(tmp_path / "s.jsonl", KEY) == (True, "")
    metrics = (tmp_path / "m.csv").read_text().splitlines()
    assert metrics[0].startswith("t_wall,step,capture_ms,inference_ms") and len(metrics) == 6
    for c in (control, reflex):
        c.close()
