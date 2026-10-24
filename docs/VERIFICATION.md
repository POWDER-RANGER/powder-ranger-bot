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

First end-to-end session on the MSI (2026-10-24, main 4c6963d + PR #10, Python 3.11):
- `pytest`: 132 passed on the MSI with the current code (review fixes included)
- `padtest --output x360`, read back over XInput: same result as 2026-10-21
- NitroGen server (RTX 4060): `ng.pt` complete (1,974,723,762 bytes), SigLIP2
  encoder downloaded. Round trip with a synthetic frame: about 225 ms per
  16-action chunk after a 1.4 s first call, about 2 GB of VRAM
- Live session, `launch --pack supertuxkart --start-game --player-input keyboard`
  with the example profile: dxcam captured the window (median 3.3 ms), NitroGen
  inferred on live frames (median 450 ms per chunk with the game running),
  151 chunks, 144 allowed by the Governor, the virtual pad drove the kart
- Play quality: poor. In about 40 s of a 1-lap Lighthouse time trial the kart
  made little progress, then the session left the race for the main menu.
  NitroGen ran unconditioned (no game selected) and has no SuperTuxKart tuning
- STOP file: tripped the kill switch, revoked the delegation, every later
  packet was denied (`halted: stop file present`); log chain OK (170 records)
- Not sealed: `launch` keeps running after a halt (by design, so the player can
  resume), and it was force-closed from a hidden window, so the seal was never
  written. End sessions with Ctrl+C in the launch window to get the seal

Defects found and fixed in that run: dxcam needs OpenCV at capture time (now in
the `windows` extra). NitroGen's own install needs `transformers<5` and
`diffusers<0.36` (newer versions break its SigLIP loading and imports), and
`HF_HUB_DISABLE_XET=1` if the encoder download stalls.

Still unverified:
- DS4 axis direction (XInput cannot read a DS4; check in joy.cpl)
- Reading a physical pad through XInput (no physical pad was connected)
- Player override during live play (keyboard source ran; no keys were pressed)
- Play quality worth calling "playing", and staying in the race
- The firewall lockdown (optional during development; netcheck is the test)
