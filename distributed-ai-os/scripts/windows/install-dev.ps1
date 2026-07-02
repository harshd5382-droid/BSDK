# Install Python dependencies for the monorepo workspace (Windows).
# PowerShell equivalent of scripts/install-dev.sh — Windows has no make/bash.
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $Root

$venv = Join-Path $Root ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    Write-Host "==> Creating venv with uv..."
    uv venv $venv
    Write-Host "==> Installing workspace packages (editable)..."
    uv pip install --python $venvPython -e "$Root\apps\node"
    uv pip install --python $venvPython -e "$Root\apps\launcher"
    # Reinstall protocol last: uv downgrades path deps to non-editable wheels
    # when installing node/launcher, which leaves stale copies in site-packages.
    uv pip install --python $venvPython -e "$Root\packages\protocol"
    uv pip install --python $venvPython pytest pytest-asyncio httpx ruff hatchling zeroconf
} else {
    if (-not (Test-Path $venvPython)) {
        Write-Host "==> Creating venv with python..."
        python -m venv $venv
    }
    Write-Host "==> Installing workspace packages (editable)..."
    & $venvPython -m pip install -U pip hatchling
    & $venvPython -m pip install -e "$Root\apps\node"
    & $venvPython -m pip install -e "$Root\apps\launcher"
    & $venvPython -m pip install -e "$Root\packages\protocol"
    & $venvPython -m pip install pytest pytest-asyncio httpx ruff
    # Native exit codes don't throw under $ErrorActionPreference = "Stop"; check explicitly.
    & $venvPython -m pip install zeroconf
    if ($LASTEXITCODE -ne 0) { Write-Warning "zeroconf install failed (mDNS discovery unavailable)" }
}

Write-Host "Installed daios-protocol, daios-node, and daios-launcher into $venv"
