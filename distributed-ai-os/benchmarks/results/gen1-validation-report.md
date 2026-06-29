# Generation 1 Validation Report

Date: 2026-06-29
Status: **Validated** — real distributed inference proven end-to-end.

## Environment

| Item | Value |
|------|-------|
| CPU | Intel Core i3-4130 @ 3.40GHz (4 threads) |
| RAM | 15 GiB |
| GPU | none (CPU-only) |
| OS | Linux 6.8 x86_64 |
| llama.cpp | commit `8c146a8` (b1), built with `-DGGML_RPC=ON` |
| Model | Qwen2.5-0.5B-Instruct, Q4_K_M GGUF (~462 MiB, 630M params) |
| Topology | Loopback two-node: coordinator + 1 RPC worker on `127.0.0.1` |

> Loopback is used because only one machine is available. llama.cpp explicitly
> supports `127.0.0.1` RPC endpoints; this exercises the identical code path a
> physical two-machine deployment uses (TCP transport, tensor serialization,
> remote backend registration). Cross-machine numbers will differ by LAN latency.

## What was proven

1. `ggml-rpc-server` (worker) exposes the CPU device over TCP :50052.
2. `llama-server` (coordinator) registers the remote RPC backend via `--rpc 127.0.0.1:50052`.
3. The worker log confirms `Accepted client connection` from the coordinator.
4. A real inference request returns coherent Qwen output (not mock).
5. The `daios-node` daemon orchestrates both processes from YAML config.
6. The node's OpenAI-compatible API works for: `/v1/models`, non-streaming
   `/v1/chat/completions`, and streaming SSE (`stream: true`).

## Benchmark: RPC-distributed vs single-node

8 requests, `max_tokens=64`, `temperature=0.7`, identical model and host.

| Configuration | Throughput (tok/s) | Latency p50 (ms) | Latency p95 (ms) | Mean (ms) |
|---------------|-------------------:|-----------------:|-----------------:|----------:|
| Single-node (no RPC) | **13.12** | 4457 | 8122 | 4868 |
| RPC-distributed (loopback) | 12.43 | 5303 | 6401 | 5111 |

Raw JSON: `gen1-single-node.json`, `gen1-rpc-distributed.json`.

Single inference timings (direct llama-server): prompt ~47 tok/s, generation ~17 tok/s.

## Interpretation

RPC-distributed is ~5% slower than single-node for this small model. This is the
**expected** Generation 1 result and confirms the Phase 1 research conclusion:

- GGML RPC pools **memory** across nodes so a cluster can run models larger than
  any single node's RAM. It does **not** parallelize compute for speed.
- For a model that already fits on one node, RPC adds network/serialization
  overhead per tensor op, so it is slightly slower.
- Therefore the Gen-1 decision to **reuse** llama.cpp + GGML RPC is correct: it
  proves distributed inference with minimal new code. A **native** distributed
  inference engine (Generation 4) should be built only if benchmarking predicts
  measurable gains — exactly as the roadmap specifies.

## Reproduce

```bash
# 1. Build llama.cpp with RPC
./scripts/build-llama-cpp.sh            # or see scripts for cmake-via-uv path

# 2. Download a small GGUF into models/
#    Qwen2.5-0.5B-Instruct-Q4_K_M used here.

# 3. Start worker then coordinator (sets LD_LIBRARY_PATH for the bundled libs)
LD_LIBRARY_PATH=.venv/bin daios-node -c examples/two-node/worker-local.yaml &
LD_LIBRARY_PATH=.venv/bin daios-node -c examples/two-node/coordinator-local.yaml &

# 4. Benchmark both configurations
python benchmarks/run_benchmark.py --url http://127.0.0.1:8000 -n 8 \
    --label rpc-distributed -o benchmarks/results/gen1-rpc-distributed.json
# (restart coordinator with coordinator-single.yaml for the baseline)
```

## Known issues found & fixed during validation

- **Subprocess pipe deadlock**: `llama-server`'s verbose startup output filled the
  unread `PIPE` buffer and stalled model loading. Fixed by redirecting child
  output to per-node log files (`DAIOS_LOG_DIR`, default system temp).
- **GGML RPC fragility**: abruptly killing `llama-server` can wedge the
  `ggml-rpc-server` accept loop (proof-of-concept limitation). Workers must be
  restarted to recover. Documented; automatic recovery is a Generation 2 concern.
