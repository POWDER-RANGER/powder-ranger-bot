# Æther field manual

How the player's channels, calibration, Game Packs and modes work. Setup is in [SETUP-WINDOWS.md](SETUP-WINDOWS.md); the system design is in [ARCHITECTURE.md](../ARCHITECTURE.md).

## Player input

`launch --player-input xinput` reads your physical pad and sends it to the
Governor as player input, which always outranks the companion. The virtual
pad is also an XInput device, so the physical pad's slot is chosen **before**
the virtual pad exists; launch refuses if zero or several pads are connected
(pass `--player-slot` to choose). Add `--steady` to smooth tremor from the
sticks. If the player input process dies, launch halts the companion.

`--player-input keyboard` reads `player_input.keymap` from the profile
(see `config/profiles/example_player.yaml`). The game also receives those
keys directly, so map switches to keys the game does not use.

## Shared control

A player packet with no claims takes the whole pad: the companion yields
everything for `player_override_hold_ms`. A packet that **claims** specific
controls (`lx`, `ly`, `rx`, `ry`, `lt`, `rt`, `buttons`) owns only those, for
`claim_ttl_ms` after each update; the companion keeps the rest. Gaze uses
this: look where you want to go and you own the steering, while the companion
keeps throttle and the other controls. Only player packets can claim.

## Gaze

```powershell
pip install -e ".[gaze]"            # MediaPipe + OpenCV; prep mode
# download face_landmarker.task (MediaPipe) to models\ in prep mode
python -m powder_ranger gaze-calibrate          # 9 dots, full screen
python -m powder_ranger launch --pack supertuxkart --player-input gaze
```

Iris position inside each eye opening is mapped to the screen by a quadratic
fit from the 9 calibration points. A deliberate long blink (450 ms or more)
taps the south button; normal blinks and lost-face frames never do.

## Voice

`launch --voice` (or `python -m powder_ranger voice`) listens locally with
faster-whisper and answers through text-to-speech on one thread. Install with
`pip install -e ".[voice]"`; the first run downloads the speech model, so do it
before the offline lockdown.

| Say | Effect |
| --- | --- |
| "stop", "halt", "freeze" | Kill switch. "Don't stop" does not trigger it. |
| "resume" | Clears the halt. The companion still needs a new grant. |
| "you play", "take over" / "you drive" | Grants full autopilot / driving |
| "my turn", "I've got it" | Revokes every delegation |
| "jump" | One press of the south button, as player input |
| "status", "help" | Spoken answer |

Squad-style orders ("move to the tower, silent", "flank left") are parsed and
logged as player intents, and answered "I can't do that yet" until the
planners exist.

## Calibration

```powershell
python -m powder_ranger calibrate record --seconds 180     # play freely with your own pad
python -m powder_ranger calibrate fit --file logs\calibration-<time>.jsonl --name me
python -m powder_ranger calibrate reaction --name me        # 20 trials, full screen
python -m powder_ranger --profile config\profiles\local_me.yaml launch --pack supertuxkart
```

Fitted from free play: button hold and gap minimums, peak press rate, stick
movement speed (Fitts slope; the intercept reads low), tremor size and
frequency. Reaction time comes only from the reaction test. On a synthetic
player with known values the fit recovers them closely (`tests/test_calibrate.py`).

## Game Packs and reports

`launch --pack supertuxkart --start-game` starts the game straight into a
1-lap time trial, applies the pack's process, pad type and allowed
delegations, and logs the pack's version and content hash. When the session
ends, launch prints the session report (`python -m powder_ranger report` for
the newest log at any time).

## Modes: deployment and development

`mode: deployment` (default) is checked against human-limit bounds at start
(`DEPLOYMENT_BOUNDS` in `config.py`); a session outside them refuses to start.

`config/profiles/development.yaml` switches to `mode: development` for
benchmarking: humanizing off, higher rates. Development runs isolated only:
it refuses `online_mode`. The kill switch, neutral-on-halt, packet validation
and focus checks are the same in both modes. A deployment session cannot
inherit development values: `tests/test_governor.py::test_dev_settings_cannot_leak_into_deployment`.

