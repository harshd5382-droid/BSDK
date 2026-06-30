#!/usr/bin/env bash
# Two-machine LAN benchmark harness for Generation 1.
# Requires COORD_HOST and WORKER_HOST env vars pointing to real machines.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS="${ROOT}/benchmarks/results/gen1-lan-2node.json"

if [[ -z "${COORD_HOST:-}" || -z "${WORKER_HOST:-}" ]]; then
  echo "SKIP: Set COORD_HOST and WORKER_HOST to run LAN two-node benchmark."
  echo "  Example: COORD_HOST=192.168.1.10 WORKER_HOST=192.168.1.20 $0"
  exit 0
fi

echo "LAN benchmark: coordinator=${COORD_HOST}, worker=${WORKER_HOST}"
echo "Ensure worker is running: daios-node -c examples/two-node/worker.yaml"
echo "Ensure coordinator is running on ${COORD_HOST}"

URL="http://${COORD_HOST}:8000"
"${ROOT}/.venv/bin/python" "${ROOT}/benchmarks/run_benchmark.py" \
  --url "${URL}" \
  -n 20 \
  --output "${RESULTS}"

echo "Results written to ${RESULTS}"
