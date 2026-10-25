<#
Æther - Windows setup (runtime only).

Creates .venv in the repo, installs Æther with Windows extras, and runs
the test suite. NitroGen keeps its own venv (it needs torch); the two talk over
a local socket only, which also keeps NitroGen's noncommercial license separate.

Usage (PowerShell, from the repo root):
  powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
#>
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

function Find-Python {
    foreach ($v in @("3.12", "3.11", "3.13")) {
        $p = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
    }
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        $p = & uv python find 3.12 2>$null
        if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
        $p = & uv python find 3.11 2>$null
        if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
    }
    throw "No Python 3.11-3.13 found. Install one with: uv python install 3.12"
}

$Py = Find-Python
Write-Host "Using $Py"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $Py -m venv .venv }
$VPy = Join-Path $Repo ".venv\Scripts\python.exe"

& $VPy -m pip install --upgrade pip | Out-Null
& $VPy -m pip install -e ".[windows,dev]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }

$vig = Get-Service -Name ViGEmBus -ErrorAction SilentlyContinue
if ($vig) { Write-Host "ViGEmBus service: $($vig.Status)" }
else { Write-Warning "ViGEmBus not found: virtual controllers will not work until it is installed." }

Write-Host "`nRunning tests..."
& $VPy -m pytest -q
Write-Host "pytest exit code: $LASTEXITCODE"
Write-Host "`nNext: scripts\start_nitrogen_server.ps1, then .venv\Scripts\python -m powder_ranger padtest"
