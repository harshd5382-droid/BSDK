#!/usr/bin/env bash
# Build llama.cpp with GGML RPC support for Generation 1 distributed inference.
set -euo pipefail

LLAMA_CPP_VERSION="${LLAMA_CPP_VERSION:-master}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/usr/local}"
BUILD_DIR="${BUILD_DIR:-/tmp/llama.cpp-build}"
SRC_DIR="${SRC_DIR:-/tmp/llama.cpp-src}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

# GPU backends: set GGML_CUDA=1 and/or GGML_VULKAN=1 in the environment.
# Without one, binaries are CPU-only and ggml-rpc-server exposes no GPU
# device — the machine's GPU/VRAM can never join the cluster pool.
BACKEND_FLAGS=()
[[ "${GGML_CUDA:-0}" == "1" ]] && BACKEND_FLAGS+=("-DGGML_CUDA=ON")
[[ "${GGML_VULKAN:-0}" == "1" ]] && BACKEND_FLAGS+=("-DGGML_VULKAN=ON")
if [[ ${#BACKEND_FLAGS[@]} -eq 0 ]]; then
  echo "WARNING: no GPU backend selected (GGML_CUDA=1 / GGML_VULKAN=1); building CPU-only binaries."
fi

echo "==> Building llama.cpp (${LLAMA_CPP_VERSION}) with GGML_RPC=ON ${BACKEND_FLAGS[*]}"

if [[ ! -d "${SRC_DIR}/.git" ]]; then
  git clone --depth 1 --branch "${LLAMA_CPP_VERSION}" \
    https://github.com/ggml-org/llama.cpp.git "${SRC_DIR}" 2>/dev/null \
    || git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "${SRC_DIR}"
fi

cd "${SRC_DIR}"
git fetch --depth 1 origin "${LLAMA_CPP_VERSION}" 2>/dev/null || true
git checkout "${LLAMA_CPP_VERSION}" 2>/dev/null || true

rm -rf "${BUILD_DIR}"
cmake -S . -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_RPC=ON \
  -DLLAMA_CURL=ON \
  "${BACKEND_FLAGS[@]}"

cmake --build "${BUILD_DIR}" --config Release -j"${JOBS}"

BINARIES=(llama-server ggml-rpc-server rpc-server llama-cli)
for bin in "${BINARIES[@]}"; do
  if [[ -f "${BUILD_DIR}/bin/${bin}" ]]; then
    sudo install -m 755 "${BUILD_DIR}/bin/${bin}" "${INSTALL_PREFIX}/bin/"
    echo "Installed ${INSTALL_PREFIX}/bin/${bin}"
  fi
done

echo ""
echo "Verify installation:"
echo "  ggml-rpc-server --help"
echo "  llama-server --help"
echo ""
echo "Generation 1 two-node usage:"
echo "  # Worker:"
echo "  ggml-rpc-server --host 0.0.0.0 -p 50052"
echo "  # Coordinator:"
echo "  llama-server -m model.gguf --rpc WORKER_IP:50052 -ngl 99"
