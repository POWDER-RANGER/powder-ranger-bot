# Windows setup

Reference machine: MSI Katana 15 (RTX 4060 Laptop, 8 GB), Windows 11.


```powershell
# 1. Runtime venv + tests
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

# 2. Check the virtual pad: open joy.cpl > Properties, then
.venv\Scripts\python -m powder_ranger padtest --output x360

# 3. NitroGen server (its own venv, weights at %USERPROFILE%\Aether\weights\ng.pt)
#    NitroGen's venv needs: pip install "transformers>=4.50,<5" "diffusers<0.36"
#    If the SigLIP2 encoder download stalls, set $env:HF_HUB_DISABLE_XET="1" first.
#    Warns if the firewall rule is missing; add -RequireFirewall to refuse instead.
powershell -ExecutionPolicy Bypass -File scripts\start_nitrogen_server.ps1

# 4. Smoke test: game running windowed in a single-player race
powershell -ExecutionPolicy Bypass -File scripts\run_smoke_test.ps1 -Process supertuxkart.exe
# or, with the pack starting the game itself:
.venv\Scripts\python -m powder_ranger launch --pack supertuxkart --start-game --player-input xinput

# Optional, for real play sessions only (Administrator). Not needed during development.
# It also blocks the base Python, which affects other projects on this machine.
powershell -ExecutionPolicy Bypass -File scripts\lockdown_offline.ps1
.venv\Scripts\python -m powder_ranger netcheck
# then add -RequireOffline to the smoke test, or --require-offline to launch
```

Results land in `logs/` (kept local, git-ignored):
`session-*.jsonl` (verify with `python -m powder_ranger verify-log <file>`) and
`reflex_metrics.csv` (capture and inference time per chunk). Packet age at
the Governor is in each intent record (`age_ms`).

