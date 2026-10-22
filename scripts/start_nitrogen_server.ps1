<#
Start NitroGen's inference server in its own venv.

NitroGen asks interactively which game to condition on. This script answers
with an empty line (unconditional), so it also works when started in the
background. It prints "Server running on port 5555" when ready.

Usage:
  powershell -ExecutionPolicy Bypass -File scripts\start_nitrogen_server.ps1
#>
param(
    [string]$NitroGenDir = "$env:USERPROFILE\Aether\NitroGen",
    [string]$Weights = "$env:USERPROFILE\Aether\weights\ng.pt",
    [int]$Port = 5555,
    [switch]$SkipFirewallCheck
)
$ErrorActionPreference = "Stop"
$py = Join-Path $NitroGenDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "NitroGen venv not found at $py" }
if (-not (Test-Path $Weights)) { throw "Weights not found at $Weights (hf download nvidia/NitroGen ng.pt --local-dir ...)" }

# serve.py binds every interface and unpickles what it receives. Do not start it unless the
# inbound rule that restricts it to this machine exists (scripts\lockdown_offline.ps1 creates it).
if (-not $SkipFirewallCheck) {
    $rule = Get-NetFirewallRule -DisplayName "PowderRanger-NitroGen-$Port-In" -ErrorAction SilentlyContinue
    if (-not $rule) {
        throw "Firewall rule 'PowderRanger-NitroGen-$Port-In' not found. Run scripts\lockdown_offline.ps1 first (or pass -SkipFirewallCheck on an isolated machine)."
    }
}

& $py -c "import torch; print('CUDA available:', torch.cuda.is_available())"
Set-Location $NitroGenDir
"" | & $py scripts\serve.py $Weights --port $Port
