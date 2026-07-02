# Build llama.cpp with GGML RPC on Windows (requires CMake + MSVC).
#
# IMPORTANT: without -Cuda or -Vulkan this produces CPU-ONLY binaries. A
# CPU-only ggml-rpc-server.exe exposes no GPU device, so a worker's GPU/VRAM
# can never be used by the cluster no matter how the coordinator is
# configured. Build with the backend matching the machine's GPU:
#   -Cuda    NVIDIA GPUs (requires CUDA Toolkit)
#   -Vulkan  any modern GPU incl. AMD/Intel (requires Vulkan SDK)
param(
    [string]$BuildDir = "$env:TEMP\llama.cpp-build",
    [string]$SrcDir = "$env:TEMP\llama.cpp-src",
    [string]$InstallDir = "",
    [switch]$Cuda,
    [switch]$Vulkan
)

$ErrorActionPreference = "Stop"

# $ErrorActionPreference = "Stop" does not fire on native exe exit codes; check explicitly.
function Assert-LastExitCode([string]$What) {
    if ($LASTEXITCODE -ne 0) { throw "$What failed with exit code $LASTEXITCODE" }
}

if (-not (Test-Path $SrcDir)) {
    git clone --depth 1 https://github.com/ggml-org/llama.cpp.git $SrcDir
    Assert-LastExitCode "git clone"
} else {
    git -C $SrcDir pull --ff-only
    Assert-LastExitCode "git pull"
}

if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }

$backendFlags = @()
if ($Cuda) { $backendFlags += "-DGGML_CUDA=ON" }
if ($Vulkan) { $backendFlags += "-DGGML_VULKAN=ON" }
if (-not $backendFlags) {
    Write-Warning "No GPU backend selected (-Cuda / -Vulkan): binaries will be CPU-only."
    Write-Warning "A CPU-only ggml-rpc-server exposes no GPU device to the cluster."
}

cmake -S $SrcDir -B $BuildDir `
    -DCMAKE_BUILD_TYPE=Release `
    -DGGML_RPC=ON `
    -DLLAMA_CURL=OFF `
    -DLLAMA_BUILD_TESTS=OFF `
    -DLLAMA_BUILD_EXAMPLES=OFF `
    @backendFlags
Assert-LastExitCode "cmake configure"

cmake --build $BuildDir --config Release --target ggml-rpc-server llama-server -j
Assert-LastExitCode "cmake build"

# Join-Path on Windows PowerShell 5.1 accepts only two arguments; nest for bin/Release.
$binDir = Join-Path (Join-Path $BuildDir "bin") "Release"
if (-not (Test-Path $binDir)) {
    $binDir = Join-Path $BuildDir "bin"
}

$rpc = Join-Path $binDir "ggml-rpc-server.exe"
$server = Join-Path $binDir "llama-server.exe"

if (-not (Test-Path $rpc)) {
    Write-Error "ggml-rpc-server.exe not found in $binDir"
}

Write-Host "Built:"
Write-Host "  $rpc"
Write-Host "  $server"

if ($InstallDir) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Copy-Item $rpc $InstallDir
    if (Test-Path $server) {
        Copy-Item $server $InstallDir
    } else {
        Write-Warning "llama-server.exe not found in $binDir; skipping (workers only need ggml-rpc-server.exe)"
    }
    Get-ChildItem $binDir -Filter "*.dll" | Copy-Item -Destination $InstallDir
    Write-Host "Installed to $InstallDir"
}
