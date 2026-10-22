"""Calibration is checked against synthetic players with KNOWN motor parameters:
generate a recording with the motor model, fit it, compare."""

import json
import random

from powder_ranger.intent import GamepadFrame, Source
from powder_ranger.motor.calibrate import fit_profile, profile_yaml
from powder_ranger.motor.model import MotorModel, MotorProfile

TRUE = MotorProfile(reaction_min_ms=0, reaction_max_ms=1, move_a_ms=80, move_b_ms=120, move_width=0.15,
                    tremor_amp=0.03, tremor_hz_min=6.0, tremor_hz_max=6.5, drift_sigma=0.0,
                    button_min_hold_ms=90, button_min_gap_ms=70, max_presses_per_sec=5)


def synth(path, seconds=120, seed=7):
    rng = random.Random(seed)
    m = MotorModel(TRUE, seed=seed)
    dt = 1 / 120
    t, next_event = 0.0, 0.0
    with open(path, "w") as fh:
        while t < seconds:
            if t >= next_event:
                kind = rng.random()
                if kind < 0.5:      # stick move, then hold
                    goal = rng.choice([-0.9, -0.6, -0.3, 0.3, 0.6, 0.9])
                    m.schedule((GamepadFrame(lx=goal),), 1000 * dt, Source.REFLEX, t)
                    next_event = t + rng.uniform(1.5, 3.0)
                else:               # a burst of taps
                    # mash for ~1 s: wants a press every 33 ms; the motor limits bind
                    frames = tuple(GamepadFrame(lx=m._target.lx,
                                                buttons=frozenset({"SOUTH"}) if (i // 2) % 2 == 0 else frozenset())
                                   for i in range(120))
                    m.schedule(frames, 1000 * dt, Source.REFLEX, t)
                    next_event = t + rng.uniform(1.5, 2.5)
            f = m.step(t)
            fh.write(json.dumps({"t": round(t, 5), "f": f.to_dict()}) + "\n")
            t += dt


def test_fit_recovers_known_parameters(tmp_path):
    rec = tmp_path / "rec.jsonl"
    synth(rec)
    p, report = fit_profile(rec)
    assert abs(p.button_min_hold_ms - 90) <= 12, report
    assert abs(p.button_min_gap_ms - 70) <= 15, report
    assert p.max_presses_per_sec <= 5, report
    assert 4.5 <= p.tremor_hz_min <= 7.5 and 5.0 <= p.tremor_hz_max <= 8.0, report
    assert 0.015 <= p.tremor_amp <= 0.045, report
    # The slope (cost per bit of difficulty) is recovered well; the intercept is biased low
    # because the slow start and end of each movement fall under the "moving" threshold.
    assert abs(p.move_b_ms - 120) <= 36, report
    assert "reaction_* (needs a stimulus test)" in report["not_fitted"]


def test_short_recording_keeps_defaults(tmp_path):
    rec = tmp_path / "rec.jsonl"
    rec.write_text("\n".join(json.dumps({"t": i / 120, "f": GamepadFrame().to_dict()}) for i in range(240)))
    p, report = fit_profile(rec)
    assert p == MotorProfile()
    assert "button_min_hold_ms" in report["kept_default"]


def test_profile_yaml_loads(tmp_path):
    from powder_ranger.config import load_settings, validate_settings
    prof = tmp_path / "fitted.yaml"
    prof.write_text(profile_yaml(MotorProfile(button_min_hold_ms=75), "tester"))
    s = load_settings(profile_path=prof)
    assert s.motor.button_min_hold_ms == 75 and s.profile_name == "tester"
    assert validate_settings(s) == []


def test_reaction_fit_recovers_lognormal_and_drops_anticipations():
    import math
    from powder_ranger.motor.calibrate import fit_reaction
    rng = random.Random(3)
    times = [math.exp(rng.gauss(math.log(260), 0.2)) for _ in range(40)] + [0.0, 0.0, 40.0]
    p, report = fit_reaction(times)
    assert report["anticipations"] == 3 and report["valid"] == 40
    assert abs(p.reaction_median_ms - 260) < 25 and abs(p.reaction_sigma - 0.2) < 0.06
    assert p.reaction_min_ms < p.reaction_median_ms < p.reaction_max_ms


def test_reaction_fit_needs_enough_trials():
    from powder_ranger.motor.calibrate import fit_reaction
    p, report = fit_reaction([250, 260, 0, 0])
    assert p == MotorProfile() and "kept_default" in report
