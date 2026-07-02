# Operations Guide

This guide covers day-2 operations for `distributed-ai-os/` across Linux/macOS and Windows.

## Install

- Linux/macOS:
  - `cd distributed-ai-os`
  - `./scripts/install-dev.sh` or `make install`
- Windows PowerShell:
  - `cd distributed-ai-os`
  - `.\scripts\windows\install-dev.ps1`

## Run Modes

- Mock cluster (no llama.cpp binaries): `make run-mock`
- Dashboard + launcher API: `make dashboard` (Windows: `.\scripts\windows\run-dashboard.ps1`)
- Direct node:
  - Coordinator: `.venv/bin/daios-node -c examples/two-node/coordinator.yaml`
  - Worker: `.venv/bin/daios-node -c examples/two-node/worker.yaml`

## Configuration Reference (Operations-Sensitive)

- `inference.backend`: `llama.cpp` or `mock`
- `inference.auto_restart`: enables subprocess restart supervision (default `true`)
- `inference.max_restarts`: restart budget per process in a 10-minute window (default `5`)
- `discovery.enabled`: `true` for Gen 2+ mDNS/gossip
- `scheduler.enabled`: Gen 3 feature flag (default `false`)
- `security.api_token`: optional Bearer token for node API

## Ports and Firewall

- Node API: `network.api_port` (default `8000`)
- GGML RPC server: `network.rpc_port` (default `50052`)
- Launcher API/dashboard serve: `8090` (launcher)
- mDNS discovery: UDP `5353` multicast

Allow LAN inbound traffic for API/RPC/mDNS on worker/coordinator hosts.

## Logs and Runtime Diagnostics

- Inference subprocess logs:
  - Controlled by `DAIOS_LOG_DIR`
  - Defaults to temp dir (`daios-logs`)
  - Files: `<node-id>-llama-server.log`, `<node-id>-rpc-server.log`
- API health:
  - `/health` for local process and resource state
  - `/api/v1/cluster` for cluster/membership shape
  - `/metrics` for generation and lease counters

## Cluster Token Handling

- `X-DAIOS-Token` is a LAN shared secret for launcher/worker control.
- Treat as credential: do not paste into logs/tickets.
- Rotate when sharing scope changes; distribute new value to all participating launchers/workers.

## Upgrade and Rollback

- Upgrade:
  1. Pull new commit/tag.
  2. Reinstall deps (`make install` or Windows install script).
  3. Restart nodes one-by-one (coordinator last for minimal disruption).
- Rollback:
  1. Checkout previous known-good commit.
  2. Reinstall deps.
  3. Restart nodes.

Gen 1/2 YAML remains backward compatible; new fields are additive.

## Worker Pause/Resume (Coordinator)

- Pause worker from RPC pool: `POST /api/v1/workers/pause` with `{ "host": "<ip-or-host>" }`
- Resume worker: `POST /api/v1/workers/resume`
- Inspect pause set: `GET /api/v1/workers/paused`

Paused workers stay in membership but are excluded from placement.
