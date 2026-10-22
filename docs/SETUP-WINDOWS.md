# Windows setup

Reference machine: MSI Katana 15 (RTX 4060 Laptop, 8 GB), Windows 11.


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

