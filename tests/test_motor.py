from powder_ranger.intent import GamepadFrame, Source
from powder_ranger.motor.filters import OneEuroFilter
from powder_ranger.motor.model import MotorModel, MotorProfile, min_jerk

DT = 1 / 120


def run(m, t0, seconds):
    out, t = [], t0
    while t < t0 + seconds:
        out.append((t, m.step(t)))
        t += DT
    return out


def test_reaction_delay_within_bounds():
    m = MotorModel(seed=1)
    samples = [m.sample_reaction_s() * 1000 for _ in range(2000)]
    assert min(samples) >= 120 and max(samples) <= 400
    assert 170 < sorted(samples)[1000] < 230           # median near 200 ms


def test_player_passes_through_without_delay():
    m = MotorModel(seed=1)
    m.schedule((GamepadFrame(lx=1.0),), 16.7, Source.PLAYER, 0.0)
    assert m.step(0.0).lx == 1.0


def test_companion_waits_then_moves_smoothly_without_overshoot():
    p = MotorProfile(tremor_amp=0.0, drift_sigma=0.0)
    m = MotorModel(p, seed=3)
    start = m.schedule((GamepadFrame(lx=1.0),), 16.7, Source.REFLEX, 0.0)
    trace = run(m, 0.0, 1.0)
    assert all(f.lx == 0.0 for t, f in trace if t < start)
    xs = [f.lx for t, f in trace if t >= start]
    assert all(b >= a - 1e-9 for a, b in zip(xs, xs[1:]))   # monotonic
    assert max(xs) <= 1.0 and xs[-1] > 0.999


def test_tremor_is_small_and_only_when_held():
    m = MotorModel(MotorProfile(reaction_min_ms=0, reaction_max_ms=1), seed=2)
    trace = run(m, 0.0, 0.5)
    assert all(f.lx == 0 and f.ly == 0 for _, f in trace)     # at rest: no tremor
    m.schedule((GamepadFrame(lx=0.5),), 16.7, Source.REFLEX, 0.5)
    late = [f.lx for _, f in run(m, 0.5, 2.0)][-60:]
    assert all(abs(x - 0.5) < 0.1 for x in late)
    assert max(late) - min(late) > 0.001                     # some tremor present


def test_button_min_hold_and_rate_cap():
    p = MotorProfile(reaction_min_ms=0, reaction_max_ms=1, button_min_hold_ms=60,
                     button_min_gap_ms=0, max_presses_per_sec=3)
    m = MotorModel(p, seed=1)
    # A one-frame tap is held for at least 60 ms.
    m.schedule((GamepadFrame(buttons=frozenset({"SOUTH"})), GamepadFrame()), 8.3, Source.REFLEX, 0.0)
    trace = run(m, 0.0, 0.3)
    down = [t for t, f in trace if "SOUTH" in f.buttons]
    assert down and (down[-1] - down[0]) >= 0.05
    # Mashing: at most 3 presses in a second.
    m2 = MotorModel(p, seed=1)
    frames = tuple(GamepadFrame(buttons=frozenset({"EAST"}) if i % 2 == 0 else frozenset())
                   for i in range(60))
    m2.schedule(frames, 16.7, Source.REFLEX, 0.0)
    trace = run(m2, 0.0, 1.0)
    presses = sum(1 for (_, a), (_, b) in zip(trace, trace[1:])
                  if "EAST" in b.buttons and "EAST" not in a.buttons) + ("EAST" in trace[0][1].buttons)
    assert presses <= 3


def test_hard_neutral_is_immediate():
    m = MotorModel(seed=1)
    m.schedule((GamepadFrame(lx=1, buttons=frozenset({"SOUTH"})),), 16.7, Source.PLAYER, 0.0)
    m.step(0.0)
    assert m.hard_neutral() == GamepadFrame()
    assert m.step(0.01) == GamepadFrame()


def test_humanize_off_for_benchmarks():
    m = MotorModel(MotorProfile(humanize=False), seed=1)
    m.schedule((GamepadFrame(lx=1.0),), 16.7, Source.REFLEX, 0.0)
    assert m.step(0.0).lx == 1.0


def test_min_jerk_endpoints():
    assert min_jerk(0) == 0 and min_jerk(1) == 1 and abs(min_jerk(0.5) - 0.5) < 1e-9


def test_one_euro_filter_reduces_jitter():
    import math
    f = OneEuroFilter(min_cutoff_hz=1.0, beta=0.0)
    raw, out = [], []
    for i in range(240):
        t = i / 120
        x = 0.5 + 0.05 * math.sin(2 * math.pi * 5 * t)     # 5 Hz tremor on a held stick
        raw.append(x)
        out.append(f(x, t))
    spread = lambda v: max(v[-120:]) - min(v[-120:])
    assert spread(out) < spread(raw) / 3
