<#
Æther - play-mode network lockdown. Run as Administrator.

  - Sets HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE for this user.
  - Blocks outbound traffic for the Æther and NitroGen Python interpreters.
  - Blocks inbound TCP 5555 (NitroGen's server listens on ALL interfaces and
    accepts pickle, which can run code) and 5577 (Governor; it already binds
    localhost only - this is defense in depth).
  - Runs `powder_ranger netcheck` to test the result. Configuration is not proof;
    the check is.

Windows venv python.exe is a launcher that starts the base interpreter, so the
base interpreter is blocked too. That blocks every project using that base
Python until you run this script with -Undo (prep mode: updates, downloads).

Usage:
  powershell -ExecutionPolicy Bypass -File scripts\lockdown_offline.ps1
  powershell -ExecutionPolicy Bypass -File scripts\lockdown_offline.ps1 -Undo
#>
param(
    [string]$NitroGenDir = "$env:USERPROFILE\Aether\NitroGen",
    [switch]$Undo
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Prefix = "PowderRanger-"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script as Administrator (firewall rules need it)."
}

if ($Undo) {
    Get-NetFirewallRule -DisplayName "$Prefix*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    [Environment]::SetEnvironmentVariable("HF_HUB_OFFLINE", $null, "User")
    [Environment]::SetEnvironmentVariable("TRANSFORMERS_OFFLINE", $null, "User")
    Write-Host "Lockdown removed (prep mode). Re-run without -Undo before play."
    exit 0
}

[Environment]::SetEnvironmentVariable("HF_HUB_OFFLINE", "1", "User")
[Environment]::SetEnvironmentVariable("TRANSFORMERS_OFFLINE", "1", "User")

$programs = @()
foreach ($venv in @("$Repo\.venv", "$NitroGenDir\.venv")) {
    $vpy = Join-Path $venv "Scripts\python.exe"
    if (Test-Path $vpy) {
        $programs += $vpy
        $base = & $vpy -c "import sys; print(getattr(sys, '_base_executable', sys.executable))"
        if ($base) { $programs += $base.Trim() }
    } else {
        Write-Warning "No venv at $venv"
    }
}
$programs = $programs | Sort-Object -Unique

Get-NetFirewallRule -DisplayName "$Prefix*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
$i = 0
foreach ($prog in $programs) {
    $i++
    New-NetFirewallRule -DisplayName "$Prefix$i-NoEgress" -Direction Outbound -Action Block -Program $prog | Out-Null
    Write-Host "Outbound blocked: $prog"
}
New-NetFirewallRule -DisplayName "${Prefix}NitroGen-5555-In" -Direction Inbound -Action Block -Protocol TCP -LocalPort 5555 | Out-Null
New-NetFirewallRule -DisplayName "${Prefix}Governor-5577-In" -Direction Inbound -Action Block -Protocol TCP -LocalPort 5577 | Out-Null
Write-Host "Inbound blocked: TCP 5555, 5577 (local loopback traffic is not affected)"

Write-Host "`nVerifying..."
& "$Repo\.venv\Scripts\python.exe" -m powder_ranger netcheck
Write-Host "netcheck exit code: $LASTEXITCODE (0 = offline)"
