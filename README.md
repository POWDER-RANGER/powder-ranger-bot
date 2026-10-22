# Powder Ranger

A local, accessibility-first game companion. The player directs; the companion
plays on their behalf, through a virtual controller, from the screen alone.

**The player is the legend; the companion is the body double.** Every
controller output traces to a player intent or to a delegation the player
granted, and the player can take control back at any instant.

Status: **Stage 1 (pipeline smoke test): code complete and unit-tested; the end-to-end run on hardware has not happened yet.**
See [What has and has not been verified](#what-has-and-has-not-been-verified),
[ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md) and the
[October 2026 code review](docs/REVIEW-2026-10.md).

## How it fits together

```
 game window ──► capture ──► NitroGen reflex runner ──┐   (separate process, never touches the pad)
                                                       │ signed IntentPackets, localhost only
 player / launcher ── grant, revoke, halt ─────────────┤
                                                       ▼
                                          ┌────── GOVERNOR ──────┐  (separate process)
                                          │ rules ─► intent log   │  hash-chained, sealed
                                          │ kill switch, focus,   │
                                          │ watchdog              │
                                          └─────────┬────────────┘
                                                    ▼
                                              motor model  (reaction time, smooth travel,
                                                    │       tremor, hold times, speed caps)
                                                    ▼
                                       virtual X360 / DS4 (ViGEmBus)  ──► game
```

| Module | Role |
| --- | --- |
| `powder_ranger/intent.py` | `GamepadFrame`, `IntentPacket`, `Delegation`; JSON wire format with HMAC-SHA256 signing |
| `governor/policy.py` | The rules, pure and unit-tested (order listed in the file) |
| `governor/governor.py` | The single path to output: verifies, decides, logs, drives the motor model and adapter |
| `governor/intent_log.py` | Append-only hash-chained log, sealed with a machine-local key |
| `governor/safety.py` | Latched kill switch (Pause key, STOP file, message) and focus check |
| `motor/model.py` | Human-like output: log-normal reaction delay, minimum-jerk travel, tremor, button timing |
| `motor/filters.py` | One Euro filter for the player's own input (tremor smoothing) |
| `output/adapters.py` | `VGamepadAdapter` (X360/DS4) and `DryRunAdapter` |
| `capture/screen.py` | Window capture with dxcam |
| `runners/nitrogen.py` | Client for NitroGen's server; converts its actions to `GamepadFrame`s |
| `inputs/player.py` | Player's own controls (physical XInput pad, keyboard or key-typing switches) sent as PLAYER packets; optional tremor smoothing |
| `inputs/commands.py`, `inputs/voice.py` | Local voice commands: word-level parser with negation; stop, resume, you play, my turn, jump |
| `motor/calibrate.py` | Record the player's pad, fit their motor profile; reaction-time test |
| `packs.py`, `packs/` | Game Packs: versioned, hashed, validated per-game settings |
| `report.py` | Session report: integrity, decisions, latency percentiles, safety events, authorship |
| `cli.py` | `launch`, `governor`, `reflex`, `player`, `voice`, `calibrate`, `packs`, `report`, `padtest`, `netcheck`, `verify-log`, `stop` |

## Safety rules (enforced in `GovernorPolicy`, tested in `tests/`)

1. Kill switch halts everything, writes neutral output first, revokes all delegations. Resume needs a new grant.
2. Packets older than their TTL are dropped; replayed or out-of-order sequence numbers are dropped.
3. Player input always passes and pre-empts the companion for `player_override_hold_ms`.
4. Companion output needs an active delegation. No delegation, no output.
5. Online mode: no full-autopilot grants; the player must have shown presence recently.
6. Companion output only while the target game window is in front.
7. Confidence floor, per-source rate limit, menu buttons stripped from companion output.
8. Watchdog: no output played for 500 ms (and nothing queued) eases the pad to neutral.
9. Shutdown and errors always leave the pad neutral; the log is sealed on close.
10. No game memory access, no code injection: the game sees only a controller.

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

## Windows setup (the MSI)

```powershell
# 1. Runtime venv + tests
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

# 2. Check the virtual pad: open joy.cpl > Properties, then
.venv\Scripts\python -m powder_ranger padtest --output x360

# 3. NitroGen server (its own venv, weights at %USERPROFILE%\Aether\weights\ng.pt)
powershell -ExecutionPolicy Bypass -File scripts\start_nitrogen_server.ps1

# 4. Play-mode lockdown (Administrator), then confirm
powershell -ExecutionPolicy Bypass -File scripts\lockdown_offline.ps1
.venv\Scripts\python -m powder_ranger netcheck

# 5. Smoke test: game running windowed in a single-player race
powershell -ExecutionPolicy Bypass -File scripts\run_smoke_test.ps1 -Process supertuxkart.exe -RequireOffline
# or, with the pack starting the game itself:
.venv\Scripts\python -m powder_ranger launch --pack supertuxkart --start-game --require-offline --player-input xinput
```

Results land in `logs/` (kept local, git-ignored):
`session-*.jsonl` (verify with `python -m powder_ranger verify-log <file>`) and
`reflex_metrics.csv` (capture and inference time per chunk). Packet age at
the Governor is in each intent record (`age_ms`).

## What has and has not been verified

Verified on the MSI (2026-10-21, Windows 11 Insider 26220, Python 3.11):
- `pytest`: 53 passed (needs the repo-local temp dir, now in `pyproject.toml`)
- `padtest --output x360`, read back over XInput: every axis reached +/-0.8 in
  the right direction (+y = up, so `invert_y: false`), LT reached 255, all 10
  buttons registered, the pad ended neutral; log chain OK, seal OK
- Governor CLI: Pause hotkey registers; a synthesized Pause keypress tripped the
  kill switch; the STOP file tripped it too
- CUDA PyTorch (torch 2.11 + cu128) sees the RTX 4060; NitroGen's dependencies import
- SuperTuxKart 1.5 installed as `supertuxkart.exe`; a virtual DS4 pad creates

Verified in the development container (Linux, Python 3.13): `python -m pytest -q`,
132 tests passing, including a headless end-to-end run (fake NitroGen and fake
capture over real ZMQ sockets to a Governor with the dry-run adapter, then a
halt and a sealed-log check), and a `governor` CLI run with `verify-log`
reporting chain OK and seal OK.

The review fixes (docs/REVIEW-2026-10.md) have not yet run on the MSI. Unverified until the MSI runs them:
- DS4 axis direction (XInput cannot read a DS4; check in joy.cpl)
- Reading a physical pad through XInput (no physical pad was connected)
- dxcam capture of the game window
- NitroGen server round trip, real inference latency, and play quality without pausing the game
- The firewall lockdown (netcheck is the test)

## NitroGen and licensing

NitroGen runs in its own venv and process, reached over a local socket. Its
code and weights are under NVIDIA's noncommercial license (research use
only). Powder Ranger's own code imports nothing from NitroGen. Powder Ranger's own code is MIT-licensed (see `LICENSE`); NitroGen's weights
are not, so check NVIDIA's terms before any use beyond research.

NitroGen's server binds all network interfaces and exchanges pickle, which
can execute code if a stranger reaches it. `lockdown_offline.ps1` blocks
inbound port 5555; keep it running only on this machine.

## History

`history/` keeps the original prototype unchanged, with notes on what carried
forward and what was retired.
