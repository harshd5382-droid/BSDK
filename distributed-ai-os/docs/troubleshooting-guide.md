# Troubleshooting Guide

## `llama-server` Fails to Start

Symptoms:
- `/v1/chat/completions` returns `503`
- `/health` shows `inference.llama_server = failed`

Checks:
- Inspect `DAIOS_LOG_DIR/<node-id>-llama-server.log`
- Confirm `inference.model_path` exists and is readable
- Ensure bundled libs are discoverable (`LD_LIBRARY_PATH` on Linux/macOS)

Important invariant:
- Subprocess output must be directed to log files, not an undrained `PIPE`, or startup can deadlock when logs fill buffers.

## mDNS Discovery Not Finding Peers

Checks:
- `discovery.enabled: true` and same `discovery.cluster_name` on all peers
- UDP 5353 multicast allowed by host firewall
- Same LAN/subnet and no client isolation on Wi-Fi AP
- Use `/api/v1/membership` to verify local membership state

## `503` from OpenAI Proxy

Common causes:
- Local `llama-server` unavailable
- Restart budget exhausted after repeated failures
- Coordinator cannot connect to local inference port

Recovery behavior:
- Proxy retries on `httpx.ConnectError` before returning `503`
- Response includes `Retry-After: 2` for client backoff
- `inference.auto_restart` supervises process recovery in background

## RPC Port Conflicts

Symptoms:
- `ggml-rpc-server` fails immediately
- Worker appears dead/unreachable in cluster

Checks:
- Verify port availability (`network.rpc_port`, default `50052`)
- Ensure only one worker process binds the same port on each host
- Change port in YAML and update peer references if needed

## GPU Not Detected

Checks:
- `nvidia-smi` is installed and functional
- Driver stack is present on worker host
- `gather_resources`/advertisement may report no GPU if probing fails

Notes:
- CPU-only operation remains supported
- Scheduler/resource logic falls back to non-GPU signals when GPU telemetry is absent
