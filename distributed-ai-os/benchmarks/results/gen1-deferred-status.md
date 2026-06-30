# Generation 1 Deferred Benchmarks

**Status:** Deferred pending hardware (2026-06-30)

These items were identified in Phase 1 as extensions, not blockers for Gen 1 sign-off. Runnable harnesses are provided; results are recorded when hardware is available.

## Deferred Items

| Item | Harness | Success Criteria |
|------|---------|------------------|
| Two physical machines over LAN | `benchmarks/run_lan_benchmark.sh` | Coherent inference; latency recorded in `gen1-lan-2node.json` |
| CPU+GPU heterogeneous split | `benchmarks/run_heterogeneous_benchmark.py` | GPU detected; tensor_split benchmark in `gen1-heterogeneous.json` |
| Model exceeding single-node RAM | `benchmarks/run_oversized_model_benchmark.py` | Single-node OOM; distributed succeeds; results in `gen1-oversized-model.json` |

## How to Run

```bash
# LAN (requires two machines)
COORD_HOST=192.168.1.10 WORKER_HOST=192.168.1.20 ./benchmarks/run_lan_benchmark.sh

# Heterogeneous (requires NVIDIA GPU)
python benchmarks/run_heterogeneous_benchmark.py

# Oversized model (requires large GGUF in models/)
python benchmarks/run_oversized_model_benchmark.py
```

Each script **skips gracefully** with a clear message when prerequisites are not met.

## Interpretation

Generation 1 loopback validation (13.1 vs 12.4 tok/s) already proved RPC overhead for small models. These deferred benchmarks validate:

1. Real LAN RTT impact (expected 1–5 ms per RPC op)
2. Heterogeneous CPU+GPU tensor placement
3. Memory pooling benefit when model weights exceed one node's RAM
