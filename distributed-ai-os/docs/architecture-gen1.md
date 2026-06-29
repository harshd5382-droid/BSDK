# Generation 1 Architecture

## Overview

Generation 1 validates the core hypothesis: **two machines can execute one inference request** by pooling memory and compute through llama.cpp's GGML RPC backend.

This is a proof-of-concept, not the final distributed AI operating system. The architecture is designed so Generation 2+ can extend components without rewriting Generation 1 interfaces.

## Node Roles

All nodes run the same `daios-node` binary. Behavior is determined by YAML configuration:

| Role | RPC Server | llama-server | OpenAI API |
|------|-----------|--------------|------------|
| `worker` | Yes | No | No |
| `coordinator` | No | Yes | Yes (proxy) |
| `hybrid` | Yes | Yes | Yes (proxy) |

## Inference Flow

1. Client sends `POST /v1/chat/completions` to the coordinator node API.
2. Coordinator proxies the request to local `llama-server` (port 8080).
3. `llama-server` schedules tensor operations across local devices and remote `ggml-rpc-server` instances via `--rpc`.
4. Model weights and KV cache are distributed proportionally to available memory on each device (local + remote).
5. Response streams back through the coordinator to the client.

## Peer Communication (Gen 1)

Generation 1 uses **manual peer configuration** in YAML. The coordinator probes worker RPC ports via TCP connect and optional HTTP `/health` checks.

The **dashboard** (`apps/dashboard`) + **launcher** (`apps/launcher`) provide a wizard UI that generates runtime YAML and spawns `daios-node` — no terminal required. Each PC runs its own launcher on `127.0.0.1:8090`.

Automatic discovery, cluster membership, and coordinator election are deferred to Generation 2 per the Phase 1 roadmap.

## Configuration Schema

See `packages/protocol/src/daios_protocol/config.py` for the canonical Pydantic models.

Key fields:

- `node_id` — unique node identifier
- `role` — `coordinator`, `worker`, or `hybrid`
- `peers[]` — manual list of `{id, host, rpc_port, api_port}`
- `inference.backend` — `llama.cpp` or `mock`
- `inference.model_path` — GGUF model path (coordinator only)
- `inference.n_gpu_layers` — layers to offload (`-ngl`)

## Build vs Buy (Generation 1)

| Component | Decision | Notes |
|-----------|----------|-------|
| Inference Engine | Reuse llama.cpp | Do not fork yet |
| Distributed Backend | Reuse GGML RPC | LAN/VPN only; insecure on open networks |
| API Gateway | Extend (thin proxy) | Wraps llama-server OpenAI API |
| Discovery | Manual config | Gen 2: libp2p or mDNS |
| Scheduler | llama.cpp default | Gen 3: custom scheduler |
| Security | None (Gen 1) | Gen 2+: TLS/mTLS |

## Validation Status (2026-06-29)

Generation 1 has been validated end-to-end on a CPU-only host using a real
llama.cpp build (`-DGGML_RPC=ON`, commit `8c146a8`) and the Qwen2.5-0.5B GGUF
model in a loopback two-node topology (coordinator + 1 RPC worker).

- Real distributed inference confirmed (worker accepts RPC client; coherent output).
- `daios-node` orchestrates `ggml-rpc-server` + `llama-server` from YAML.
- OpenAI API validated: `/v1/models`, non-streaming and streaming `/v1/chat/completions`.
- Benchmark: single-node 13.1 tok/s vs RPC-distributed 12.4 tok/s (~5% RPC overhead).

Full results: `benchmarks/results/gen1-validation-report.md`.

Two production fixes landed during validation:
1. Subprocess output is redirected to log files (`DAIOS_LOG_DIR`) to avoid a
   PIPE-buffer deadlock that stalled `llama-server` model loading.
2. The OpenAI proxy detects streaming by parsing the request body (robust to
   whitespace) in addition to the `Accept: text/event-stream` header.

## Known Limitations

- GGML RPC is proof-of-concept and **must not** be exposed to the public internet.
- RPC adds network latency per tensor op; benefits are primarily for models exceeding single-node memory.
- No automatic failover, discovery, or multi-coordinator support in Gen 1.
- Binary names vary by llama.cpp version (`ggml-rpc-server` vs `rpc-server`); both are tried.

## Compatibility with Future Generations

| Gen 1 Interface | Gen 2+ Extension |
|----------------|------------------|
| `NodeConfig` YAML | Add discovery fields; keep backward compat |
| `GET /health` | Add scheduler/coordinator metrics |
| `GET /api/v1/cluster` | Add dynamic membership, coordinator election |
| OpenAI `/v1/*` | Stable public API across all generations |
| `daios-node` binary | Same binary, feature flags per generation |
