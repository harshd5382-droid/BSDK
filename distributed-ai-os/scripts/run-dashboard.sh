#!/usr/bin/env bash
# Build dashboard and start daios-launcher with browser.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

./scripts/install-dev.sh

echo "==> Building dashboard..."
cd apps/dashboard
npm install
npm run build
cd "${ROOT}"

export DAIOS_ROOT="${ROOT}"
echo "==> Starting launcher at http://127.0.0.1:8090"
exec "${ROOT}/.venv/bin/daios-launcher" --root "${ROOT}" --open "$@"
