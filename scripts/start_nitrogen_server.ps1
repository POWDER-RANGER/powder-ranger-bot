<#
Start NitroGen's inference server in its own venv.

NitroGen asks interactively which game to condition on. This script answers
with an empty line (unconditional), so it also works when started in the
background. It prints "Server running on port 5555" when ready.

Usage:
  powershell -ExecutionPolicy Bypass -File scripts\start_nitrogen_server.ps1
  ... -RequireFirewall    refuse to start unless the inbound 5555 block rule exists

During development the firewall rule is checked but only warned about, so the
server starts without the lockdown. Use -RequireFirewall for real sessions.
#>
param(
    [string]$NitroGenDir = "$env:USERPROFILE\Aether\NitroGen",
    [string]$Weights = "$env:USERPROFILE\Aether\weights\ng.pt",
    [int]$Port = 5555,
    [switch]$RequireFirewall,
    [switch]$SkipFirewallCheck     # kept for compatibility; the check now only warns unless -RequireFirewall
)
$ErrorActionPreference = "Stop"
$py = Join-Path $NitroGenDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "NitroGen venv not found at $py" }
if (-not (Test-Path $Weights)) { throw "Weights not found at $Weights (hf download nvidia/NitroGen ng.pt --local-dir ...)" }

# serve.py binds every interface and unpickles what it receives. The inbound rule from
# scripts\lockdown_offline.ps1 restricts it to this machine. Development: warn. -RequireFirewall: refuse.
$rule = Get-NetFirewallRule -DisplayName "PowderRanger-NitroGen-$Port-In" -ErrorAction SilentlyContinue
if (-not $rule) {
    $msg = "Firewall rule 'PowderRanger-NitroGen-$Port-In' not found: port $Port is reachable from your local network while the server runs."
    if ($RequireFirewall) { throw "$msg Run scripts\lockdown_offline.ps1 first." }
    Write-Warning "$msg Fine on a trusted network during development."
}

& $py -c "import torch; print('CUDA available:', torch.cuda.is_available())"
Set-Location $NitroGenDir
"" | & $py scripts\serve.py $Weights --port $Port
