# Build llama.cpp with GGML RPC on Windows (requires CMake + MSVC).
param(
    [string]$BuildDir = "$env:TEMP\llama.cpp-build",
    [string]$SrcDir = "$env:TEMP\llama.cpp-src",
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SrcDir)) {
    git clone --depth 1 https://github.com/ggml-org/llama.cpp.git $SrcDir
}

if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }

cmake -S $SrcDir -B $BuildDir `
    -DCMAKE_BUILD_TYPE=Release `
    -DGGML_RPC=ON `
    -DLLAMA_CURL=OFF `
    -DLLAMA_BUILD_TESTS=OFF `
    -DLLAMA_BUILD_EXAMPLES=OFF

cmake --build $BuildDir --config Release --target ggml-rpc-server llama-server -j

$binDir = Join-Path $BuildDir "bin" "Release"
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
    Copy-Item $server $InstallDir
    Get-ChildItem $binDir -Filter "*.dll" | Copy-Item -Destination $InstallDir
    Write-Host "Installed to $InstallDir"
}
