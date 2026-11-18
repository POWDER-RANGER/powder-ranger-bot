# File tree

Every tracked file in the repository, as a snapshot on 2026-10-25. One line per file. Regenerate this file by hand when files move.

Names that stay as they are, on purpose:
- `powder_ranger` (package and import path) and `powder-ranger` (CLI and install name): code identifiers.
- `~/.powder_ranger/` (STOP file and log key): paths on your machine. Renaming them would orphan existing logs and the stop file.
- `POWDER-RANGER/` in URLs: the GitHub organization.
- `history/` is the first prototype, kept unchanged. Do not edit it.

Display names: Æther for the platform, PR-REX for the companion. See [BRAND.md](BRAND.md).

```text
powder-ranger-bot/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml                              # Bug report form
│   │   ├── config.yml                                  # Issue chooser: blank issues on; security reports go to private advisories
│   │   └── field_report.yml                            # Field report form (what a player or tester saw)
│   ├── workflows/
│   │   └── ci.yml                                      # CI: tests on Ubuntu and Windows (Python 3.11, 3.13) and ruff lint
│   ├── dependabot.yml                                  # Dependency update schedule
│   └── pull_request_template.md                        # Pull request checklist
├── assets/
│   ├── fonts/
│   │   ├── BigShouldersDisplay-subset.woff2            # Display typeface, subset (SIL OFL 1.1)
│   │   └── OFL.txt                                     # Font license for Big Shoulders Display
│   ├── aether-learning.svg                             # Diagram: how it learns (not linked from README or site yet)
│   ├── aether-operating-path.svg                       # Diagram: operating path (not linked from README or site yet)
│   ├── aether-with-the-legend.svg                      # Diagram: control with the Legend; companion box labeled PR-REX (not linked yet)
│   ├── architecture.svg                                # Operating picture: every input travels as a signed packet to the Governor
│   ├── banner.svg                                      # README hero banner (1280x360)
│   ├── social-preview.png                              # Link-preview image (og:image), 1280x640, rendered from the SVG
│   └── social-preview.svg                              # Source for the social preview image
├── config/
│   ├── profiles/
│   │   ├── development.yaml                            # Profile for isolated benchmarking; refuses online mode
│   │   └── example_player.yaml                         # Example player profile to copy and adjust (keymap, pad settings)
│   └── default.yaml                                    # Default settings: mode, endpoint, tick rate, governor rules, motor model
├── docs/
│   ├── BRAND.md                                        # Brand and visual baseline: names, colors, type, logo, voice, asset inventory
│   ├── FIELD-MANUAL.md                                 # Player's guide: input channels, shared control, gaze, voice, calibration, packs, modes
│   ├── REVIEW-2026-10.md                               # October 2026 code review: findings F1 to F13 and their status
│   ├── SETUP-WINDOWS.md                                # Windows install, pad check, NitroGen server, smoke test
│   ├── TREE.md                                         # This file
│   └── VERIFICATION.md                                 # Record of what has run, where, and what has not
├── history/
│   ├── original_mgsv_prototype/
│   │   ├── mgsv_accessibility_integration.py           # Original accessibility integration layer (unchanged, not run)
│   │   ├── mgsv_autonomous_assistant.py                # Original core implementation (unchanged, not run)
│   │   ├── mgsv_autonomous_assistant_architecture.txt  # Original architecture roadmap (planned phases, not built)
│   │   ├── requirements.txt                            # Original dependencies (unchanged)
│   │   ├── script.py                                   # Original script fragment (unchanged)
│   │   ├── script_1.py                                 # Original script fragment (unchanged)
│   │   ├── script_2.py                                 # Original script fragment (unchanged)
│   │   ├── script_3.py                                 # Original script fragment (unchanged)
│   │   ├── SETUP_GUIDE.md                              # Original setup guide (unchanged)
│   │   └── SHA256SUMS                                  # Hashes of the prototype files as of 2026-10-21
│   └── README.md                                       # The first prototype: what carried forward and what was retired
├── packs/
│   ├── supertuxkart/
│   │   └── pack.yaml                                   # SuperTuxKart pack: process, launch arguments, allowed scopes
│   └── README.md                                       # What a Game Pack is; versioning, hashing, validation
├── powder_ranger/
│   ├── capture/
│   │   ├── __init__.py                                 # Package marker
│   │   └── screen.py                                   # Window capture of the game (dxcam, Windows)
│   ├── governor/
│   │   ├── __init__.py                                 # Package marker
│   │   ├── client.py                                   # Client for the Governor channel; every producer sends through it
│   │   ├── governor.py                                 # The Governor: the single path between every decision-maker and the controller
│   │   ├── intent_log.py                               # Append-only hash-chained log; sealing with a machine-local key
│   │   ├── policy.py                                   # Governor rules: pure logic, no I/O, unit-tested
│   │   └── safety.py                                   # Kill switch and focus check
│   ├── inputs/
│   │   ├── __init__.py                                 # Package marker
│   │   ├── commands.py                                 # Spoken command parser (word-level, negation-aware)
│   │   ├── gaze.py                                     # Webcam gaze: look to steer, dwell to select, long blink to confirm
│   │   ├── player.py                                   # Player's own controls (XInput pad, keyboard) sent as player packets
│   │   └── voice.py                                    # Local speech to commands to the Governor; nothing leaves the machine
│   ├── motor/
│   │   ├── __init__.py                                 # Package marker
│   │   ├── calibrate.py                                # Records a player's pad, fits a motor profile, runs the reaction test
│   │   ├── filters.py                                  # One Euro filter for the player's own input (tremor smoothing)
│   │   └── model.py                                    # Motor model: human-like timing, travel, tremor and button limits
│   ├── output/
│   │   ├── __init__.py                                 # Package marker
│   │   └── adapters.py                                 # Virtual pad adapters (X360, DS4) and the dry-run adapter
│   ├── runners/
│   │   ├── __init__.py                                 # Package marker
│   │   └── nitrogen.py                                 # Reflex runner: NitroGen proposes, the Governor decides
│   ├── __init__.py                                     # Package docstring: Æther; the companion is PR-REX
│   ├── __main__.py                                     # Lets python -m powder_ranger run the CLI
│   ├── cli.py                                          # Command-line entry point: launch, governor, reflex, padtest, player, voice, calibrate, gaze-calibrate, packs, report, netcheck, verify-log, stop
│   ├── config.py                                       # Loads config/default.yaml and an optional player profile
│   ├── intent.py                                       # IntentPacket, GamepadFrame, Delegation; HMAC-SHA256 signing and verification
│   ├── packs.py                                        # Loads, validates and hashes Game Packs
│   └── report.py                                       # Session report: what happened, how fast, whose session it was
├── scripts/
│   ├── lockdown_offline.ps1                            # Optional play-mode network lockdown (run as Administrator)
│   ├── run_smoke_test.ps1                              # Stage 1 smoke test: pad check, launch, then verify the log
│   ├── setup_windows.ps1                               # Creates .venv, installs with Windows extras, runs the tests
│   └── start_nitrogen_server.ps1                       # Starts the NitroGen server (port 5555) from its own environment
├── tests/
│   ├── conftest.py                                     # Shared test fixtures
│   ├── test_calibrate.py                               # Tests: calibration against synthetic players with known motor parameters
│   ├── test_gaze.py                                    # Tests: gaze input
│   ├── test_governor.py                                # Tests: the Governor and its client
│   ├── test_intent_and_log.py                          # Tests: signing, verification, hash-chained log, seal
│   ├── test_motor.py                                   # Tests: motor model timing and limits
│   ├── test_packs.py                                   # Tests: Game Pack loading, validation, hashing
│   ├── test_player_input.py                            # Tests: player input channel
│   ├── test_policy.py                                  # Tests: Governor rules
│   ├── test_report.py                                  # Tests: session report
│   ├── test_review_regressions.py                      # Regression tests for defects from the October 2026 review
│   ├── test_shared_control.py                          # Tests: shared-control arbiter
│   └── test_voice.py                                   # Tests: voice command parser and dispatcher
├── .gitignore                                          # Keeps session logs, recordings, profiles in use, caches and venvs out of git
├── .nojekyll                                           # Empty marker: tells GitHub Pages not to run Jekyll
├── ARCHITECTURE.md                                     # Processes, packet life, motor scheduling, stop path, modes, packs
├── CONTRIBUTING.md                                     # How to contribute; a test for every behavior change
├── index.html                                          # GitHub Pages site (steel theme)
├── LICENSE                                             # MIT license
├── pyproject.toml                                      # Package metadata, dependencies, extras, CLI entry point
├── README.md                                           # Front page: banner, status, quick start, documentation index, module map
└── SECURITY.md                                         # Threat model, trust boundaries, known limits, how to report
```
