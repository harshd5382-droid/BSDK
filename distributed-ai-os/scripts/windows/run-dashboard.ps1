# Build dashboard and start daios-launcher with browser (Windows).
# PowerShell equivalent of scripts/run-dashboard.sh — Windows has no make/bash.
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $Root

& (Join-Path $PSScriptRoot "install-dev.ps1") -Root $Root

Write-Host "==> Building dashboard..."
Push-Location (Join-Path $Root "apps\dashboard")
try {
    # Native exit codes don't throw under $ErrorActionPreference = "Stop"; check explicitly.
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

$env:DAIOS_ROOT = $Root
$launcher = Join-Path $Root ".venv\Scripts\daios-launcher.exe"
Write-Host "==> Starting launcher at http://127.0.0.1:8090"
& $launcher --root $Root --open @args
