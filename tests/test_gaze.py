import numpy as np
from conftest import FakeClock

from powder_ranger.inputs.gaze import (
    BlinkDetector,
    DwellSelector,
    GazeCalibration,
    GazeSource,
    GazeStick,
    Zone,
    calibration_targets,
    eye_aspect_ratio,
    eye_features,
)

W, H = 1920, 1080


def true_map(f):
    """A made-up but smooth 'eye -> screen' relationship with curvature."""
    x, y = f[..., 0], f[..., 1]
    return np.stack([W * (0.5 + 2.2 * (x - 0.5) + 0.8 * (x - 0.5) ** 2),
                     H * (0.5 + 2.6 * (y - 0.5) - 0.5 * (x - 0.5) * (y - 0.5))], axis=-1)


def test_calibration_fits_and_predicts_unseen_points():
    rng = np.random.default_rng(1)
    feats = np.array([[x, y] for y in (0.32, 0.5, 0.68) for x in (0.32, 0.5, 0.68)])
    targets = true_map(feats) + rng.normal(0, 8, (9, 2))          # 8 px of noise
    cal = GazeCalibration()
    assert cal.fit(feats, targets) < 20
    test = rng.uniform(0.35, 0.65, (50, 2))
    err = np.linalg.norm(cal(test) - true_map(test), axis=1)
    assert float(np.median(err)) < 30                               # px
    restored = GazeCalibration.from_dict(cal.to_dict())
    assert np.allclose(restored(test), cal(test))


def test_calibration_targets_cover_the_screen():
    t = calibration_targets(W, H)
    assert len(t) == 9 and t[0].tolist() == [192.0, 108.0] and t[4].tolist() == [960.0, 540.0]


def test_eye_features_and_ear_from_landmarks():
    lm = np.zeros((478, 2))
    for outer, inner, top, bottom, iris, ox in ((33, 133, 159, 145, 468, 0.3), (362, 263, 386, 374, 473, 0.6)):
        lm[outer], lm[inner] = (ox, 0.5), (ox + 0.1, 0.5)
        lm[top], lm[bottom] = (ox + 0.05, 0.48), (ox + 0.05, 0.52)
        lm[iris] = (ox + 0.075, 0.5)                                # iris 3/4 across
    f = eye_features(lm)
    assert abs(f[0] - 0.75) < 1e-6 and abs(f[1] - 0.5) < 1e-6
    for pts, ox in (((33, 160, 158, 133, 153, 144), 0.3), ((362, 385, 387, 263, 373, 380), 0.6)):
        p1, p2, p3, p4, p5, p6 = pts
        lm[p1], lm[p4] = (ox, 0.5), (ox + 0.1, 0.5)
        lm[p2], lm[p3] = (ox + 0.03, 0.485), (ox + 0.07, 0.485)
        lm[p6], lm[p5] = (ox + 0.03, 0.515), (ox + 0.07, 0.515)
    assert abs(eye_aspect_ratio(lm) - 0.3) < 1e-6


def test_blink_only_fires_on_deliberate_long_blink():
    b = BlinkDetector(closed_ear=0.17, hold_ms=450)
    t, fired = 0.0, []
    def run(ear, ms):
        nonlocal t
        for _ in range(int(ms / 10)):
            fired.append(b.update(ear, t)); t += 0.01
    run(0.3, 200); run(0.1, 200); run(0.3, 200)     # normal blink
    assert not any(fired)
    run(None, 300); run(0.3, 100)                   # face lost
    assert not any(fired)
    run(0.1, 700); run(0.3, 100)                    # deliberate blink
    assert sum(fired) == 1


def test_dwell_selects_after_holding_and_once():
    d = DwellSelector([Zone("left", 0, 0, 500, 1080), Zone("right", 1420, 0, 1920, 1080)], dwell_ms=900)
    picks = []
    t = 0.0
    for p in [np.array([100, 500])] * 50 + [np.array([960, 500])] * 10 + [np.array([1700, 500])] * 120:
        picks.append(d.update(p, t)); t += 0.02
    assert [x for x in picks if x] == ["left", "right"]


def test_gaze_stick_dead_zone_and_full_lock():
    s = GazeStick(W, H, dead=0.12, full=0.8)
    assert s(np.array([960, 540])) == (0.0, 0.0)
    assert s(np.array([960 + 0.05 * 960, 540]))[0] == 0.0
    assert s(np.array([1919, 540]))[0] == 1.0 and s(np.array([0, 540]))[0] == -1.0


def test_gaze_source_steers_and_blink_taps():
    cal = GazeCalibration()
    feats = np.array([[x, y] for y in (0.3, 0.5, 0.7) for x in (0.3, 0.5, 0.7)])
    cal.fit(feats, true_map(feats))
    c = FakeClock(0.0)
    state = {"f": np.array([0.68, 0.5]), "ear": 0.3}
    src = GazeSource(lambda: (state["f"], state["ear"]), cal, GazeStick(W, H), clock=c)
    for _ in range(60):
        f = src.read(); c.advance(1 / 60)
    assert f.lx > 0.5 and not f.buttons                 # looking right -> steer right
    state["ear"] = 0.05
    taps = []
    for _ in range(40):
        taps.append("SOUTH" in src.read().buttons); c.advance(1 / 60)
    assert any(taps)                                    # long blink tapped once
    assert src.read().lx > 0.5                          # steering held while eyes shut
