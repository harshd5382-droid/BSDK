# Build the self-contained daios-worker.exe with PyInstaller.
# Run on Windows x64 with Python 3.11+.
#
# Optional: -BinDir <path> stages prebuilt ggml-rpc-server.exe + GGML DLLs into
# packaging/windows/bin/ so they are bundled into the exe (fully offline install).
# Without it, the installer downloads + SHA-256-verifies them at runtime.
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$BinDir = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location $Root

# $ErrorActionPreference = "Stop" does not fire on native exe exit codes; check explicitly.
function Assert-LastExitCode([string]$What) {
    if ($LASTEXITCODE -ne 0) { throw "$What failed with exit code $LASTEXITCODE" }
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { Write-Error "Python 3.11+ is required to build the exe." }

Write-Host "==> Installing BSDK packages (all three) + PyInstaller..."
& $python -m pip install -e packages/protocol -e apps/node -e apps/launcher
Assert-LastExitCode "pip install (BSDK packages)"
& $python -m pip install pyinstaller
Assert-LastExitCode "pip install pyinstaller"

# Stage prebuilt native binaries for bundling, if provided.
$pkgBin = Join-Path $Root "packaging\windows\bin"
if ($BinDir) {
    if (-not (Test-Path $BinDir)) { Write-Error "BinDir not found: $BinDir" }
    New-Item -ItemType Directory -Force -Path $pkgBin | Out-Null
    Copy-Item (Join-Path $BinDir "ggml-rpc-server.exe") $pkgBin -ErrorAction Stop
    Get-ChildItem $BinDir -Filter "*.dll" | Copy-Item -Destination $pkgBin
    $llama = Join-Path $BinDir "llama-server.exe"
    if (Test-Path $llama) { Copy-Item $llama $pkgBin }
    Write-Host "==> Bundling native binaries from $BinDir"
} elseif (Test-Path $pkgBin) {
    Write-Host "==> Bundling native binaries already staged in $pkgBin"
} else {
    Write-Warning "No native binaries staged; the installer will download + verify them at runtime."
}

Write-Host "==> Building daios-worker.exe..."
# Use an array: on PowerShell 7.3+ an empty-string arg is passed literally and
# PyInstaller's argparse rejects it as a stray positional.
$extraArgs = @()
if ($Clean) { $extraArgs += "--clean" }
& $python -m PyInstaller packaging/windows/daios-worker.spec --noconfirm @extraArgs
Assert-LastExitCode "PyInstaller"

$dist = Join-Path $Root "dist\daios-worker.exe"
if (Test-Path $dist) {
    $size = [math]::Round((Get-Item $dist).Length / 1MB, 1)
    Write-Host "Built: $dist ($size MB)"
} else {
    Write-Error "Build failed - dist\daios-worker.exe not found"
}
