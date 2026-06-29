#!/usr/bin/env bash
# Install Python dependencies for the monorepo workspace.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/.venv"

if command -v uv >/dev/null 2>&1; then
  uv venv "${VENV}" 2>/dev/null || true
  uv pip install --python "${VENV}/bin/python" -e "${ROOT}/packages/protocol"
  uv pip install --python "${VENV}/bin/python" -e "${ROOT}/apps/node"
  uv pip install --python "${VENV}/bin/python" -e "${ROOT}/apps/launcher"
  uv pip install --python "${VENV}/bin/python" pytest pytest-asyncio httpx ruff hatchling
else
  if [[ ! -d "${VENV}" ]]; then
    python3 -m venv "${VENV}"
  fi
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
  pip install -U pip hatchling
  pip install -e "${ROOT}/packages/protocol"
  pip install -e "${ROOT}/apps/node"
  pip install -e "${ROOT}/apps/launcher"
  pip install pytest pytest-asyncio httpx ruff
fi

echo "Installed daios-protocol, daios-node, and daios-launcher into ${VENV}"
