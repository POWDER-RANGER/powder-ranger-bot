# Verification record

What has run, where, and what has not. Updated whenever a run changes the picture.

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

The review fixes (REVIEW-2026-10.md) have not yet run on the MSI. Unverified until the MSI runs them:
- DS4 axis direction (XInput cannot read a DS4; check in joy.cpl)
- Reading a physical pad through XInput (no physical pad was connected)
- dxcam capture of the game window
- NitroGen server round trip, real inference latency, and play quality without pausing the game
- The firewall lockdown (netcheck is the test)
