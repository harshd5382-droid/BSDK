# Build daios-worker.exe with PyInstaller (run on Windows with Python 3.11+).
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $Root

Write-Host "==> Installing launcher package..."
python -m pip install -e apps/launcher -e packages/protocol

Write-Host "==> Installing PyInstaller..."
python -m pip install pyinstaller

Write-Host "==> Building daios-worker.exe..."
python -m PyInstaller packaging/windows/daios-worker.spec --noconfirm --clean

$dist = Join-Path $Root "dist" "daios-worker.exe"
if (Test-Path $dist) {
    Write-Host "Built: $dist"
} else {
    Write-Error "Build failed — dist/daios-worker.exe not found"
}
