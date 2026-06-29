#!/usr/bin/env bash
# Start a mock two-node cluster for local validation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/.venv"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

WORKER_CONFIG="${ROOT}/examples/two-node/worker-mock.yaml"
COORD_CONFIG="${ROOT}/examples/two-node/coordinator-mock.yaml"

cleanup() {
  [[ -n "${WORKER_PID:-}" ]] && kill "${WORKER_PID}" 2>/dev/null || true
  [[ -n "${COORD_PID:-}" ]] && kill "${COORD_PID}" 2>/dev/null || true
}
trap cleanup EXIT

echo "Starting worker node..."
daios-node -c "${WORKER_CONFIG}" &
WORKER_PID=$!
sleep 2

echo "Starting coordinator node..."
daios-node -c "${COORD_CONFIG}" &
COORD_PID=$!
sleep 2

echo ""
echo "Cluster running:"
echo "  Worker API:      http://127.0.0.1:8001/health"
echo "  Coordinator API: http://127.0.0.1:8000/health"
echo "  OpenAI API:      http://127.0.0.1:8000/v1/chat/completions"
echo ""
echo "Test inference:"
echo '  curl -s http://127.0.0.1:8000/v1/chat/completions \'
echo '    -H "Content-Type: application/json" \'
echo '    -d '"'"'{"model":"daios-mock-7b","messages":[{"role":"user","content":"Hello"}]}'"'"' | jq'
echo ""
echo "Press Ctrl+C to stop."

wait
