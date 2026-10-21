<#
Stage 1 smoke test: NitroGen drives an open-source game through the Governor.

Before running:
  1. scripts\setup_windows.ps1 passed its tests
  2. padtest checked the virtual pad (python -m powder_ranger padtest)
  3. NitroGen server is running (scripts\start_nitrogen_server.ps1)
  4. The game is running windowed, in a single-player race, controller enabled
  5. For the offline gate: scripts\lockdown_offline.ps1 (Admin), Wi-Fi off

Stop at any time: Pause key, Ctrl+C here, or `python -m powder_ranger stop`.
Results: logs\session-*.jsonl (verify with verify-log) and logs\reflex_metrics.csv.
#>
param(
    [string]$Process = "supertuxkart.exe",
    [ValidateSet("x360", "ds4", "dryrun")][string]$Output = "x360",
    [switch]$RequireOffline
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$py = ".venv\Scripts\python.exe"

if (Test-Path STOP) { throw "STOP file present. Delete it to start." }
if (-not (Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($Process)) -ErrorAction SilentlyContinue)) {
    throw "$Process is not running. Start the game first (check the exact name in Task Manager)."
}

$launchArgs = @("-m", "powder_ranger", "launch", "--process", $Process, "--output", $Output, "--delegate", "full_autopilot")
if ($RequireOffline) { $launchArgs += "--require-offline" }

Write-Host "Click into the game window within 5 seconds (companion output requires focus)."
Start-Sleep -Seconds 5
& $py @launchArgs
Write-Host "launch exit code: $LASTEXITCODE"

$latest = Get-ChildItem logs\session-*.jsonl | Sort-Object LastWriteTime | Select-Object -Last 1
if ($latest) { & $py -m powder_ranger verify-log $latest.FullName }
