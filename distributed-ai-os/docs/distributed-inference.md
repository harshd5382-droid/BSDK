# Distributed Inference: Resource Balancing over GGML RPC

This document explains what llama.cpp's GGML RPC backend can and cannot
distribute, why a BSDK coordinator used to do almost all the work, how the
distribution policy fixes that, and how to validate the result on two real
Windows PCs.

---

## 1. What GGML RPC actually distributes

BSDK runs one `llama-server` on the coordinator and one `ggml-rpc-server`
per worker, connected via `--rpc host:port,...`. It is **not** symmetrical
distributed inference. Precisely:

| Concern | Distributed? | How |
|---|---|---|
| Model tensor storage (weights) | **Yes** | Split across all GPU-class devices — local GPUs and every RPC device — per `--tensor-split` (default: proportional to each device's free memory) |
| KV cache | **Yes** | Stored with the layers: each device holds the KV cache for the layers it owns |
| Prompt processing / token generation compute | **Yes, follows placement** | Layer (pipeline) parallelism: a layer's matmuls run on the device holding that layer, including remote RPC devices |
| GPU VRAM on workers | **Only if** the worker's `ggml-rpc-server` was **built with a GPU backend** (CUDA/Vulkan). A CPU-only build exposes one CPU device backed by system RAM |
| System RAM on workers | **Yes** — via a CPU-backed RPC device (slow compute; memory ≠ speed) |
| Model loading | Partially | The coordinator reads the GGUF and streams tensor data to each device over the network at load time |
| Backend initialization | Per machine | Each rpc-server initializes its *own* backends; the coordinator cannot give a worker GPU support its binary doesn't have |
| Tokenization, sampling, logits/output | **No — always coordinator** | The output layer readback, sampling loop, and all HTTP/orchestration stay on the coordinator |
| Non-offloaded layers (`-ngl` < all) | **No** | They run on the coordinator CPU in coordinator system RAM |
| Graph orchestration / scheduling | **No** | ggml's scheduler runs on the coordinator; per-token it walks the graph and dispatches ops to devices in sequence |

Two consequences worth stating honestly:

- **System RAM and GPU VRAM are different resources.** A worker "contributing
  8 GB" via a CPU-only rpc-server contributes 8 GB of *RAM plus slow CPU
  compute*, not VRAM. Nothing can make a remote CPU device fast.
- **Token generation is latency-bound.** Layer-split inference crosses the
  network at every device boundary *for every token*. On gigabit LAN this
  costs roughly 0.5–2 ms per boundary per token; more devices ≠ more speed.
  The honest win of RPC pooling is **capacity** (run a model that doesn't
  fit on one machine), with speed gains only when the worker device is much
  faster than what the coordinator would otherwise use (e.g. worker GPU vs
  coordinator CPU spill).

llama.cpp **cannot attach RPC devices to an already-loaded model.** Changing
the device set requires restarting `llama-server` (see §5).

## 2. Why the coordinator did almost all the work (root causes)

Identified in this codebase, with evidence:

1. **Gen 2 startup race — model loaded with no `--rpc` at all.**
   `InferenceManager.start()` launched `llama-server` immediately at boot.
   With discovery enabled, `_peer_hosts` was still `None` and Gen 2 YAMLs
   have an empty `peers[]`, so `rpc_endpoints()` returned nothing: the model
   loaded 100 % locally. Workers discovered afterwards triggered an *inline*
   restart from whatever request happened to call `set_peer_hosts` first —
   killing in-flight requests, or never happening at all if no one polled.
2. **CPU-only worker binaries on Windows.**
   `scripts/windows/build-llama-cpp.ps1` configured llama.cpp with only
   `-DGGML_RPC=ON` — no `GGML_CUDA`/`GGML_VULKAN`. The resulting
   `ggml-rpc-server.exe` exposes no GPU device, so worker VRAM/GPU could
   never participate regardless of configuration. (Fixed: `-Cuda` /
   `-Vulkan` switches; the script now warns loudly when building CPU-only.)
3. **No tensor-split control.** BSDK never generated `--tensor-split`;
   llama.cpp's default splits weights + KV proportional to *free device
   memory*. A coordinator with a 24 GB GPU next to a worker's 8 GB device
   takes 75 % by design — and there was no way to express reserves,
   worker preference, or latency awareness.
4. **No readiness gate or capability validation.** `llama-server` could
   start before the worker's RPC port accepted connections, and nothing
   reported whether a worker was GPU-enabled, so a CPU-only worker looked
   identical to a GPU worker until you read llama-server logs by hand.
5. **Unsafe, undebounced topology restarts.** Any peer-set change restarted
   `llama-server` immediately — flapping discovery could restart it in a
   loop, mid-request.

## 3. The distribution policy (opt-in)

Add `inference.distribution` to a coordinator YAML (see
`examples/two-node/coordinator-distributed.yaml`). Without the block,
behavior is exactly the legacy path — existing Gen 1/Gen 2/mock YAMLs work
unchanged.

```yaml
inference:
  backend: llama.cpp
  model_path: /models/model.gguf
  distribution:
    policy: auto            # auto | balanced | worker_preferred | manual
    coordinator_reserve_ram_gb: 4
    coordinator_reserve_vram_gb: 1
    worker_reserve_ram_gb: 2
    worker_reserve_vram_gb: 0.5
    minimum_worker_vram_gb: 0
    wait_for_workers_seconds: 30
    restart_debounce_seconds: 10
    # manual_allocations: { worker-1: 0.7, coordinator-1: 0.3 }
```

How a launch works with distribution enabled:

1. **Wait for workers.** Every desired RPC endpoint is TCP-probed until
   reachable or `wait_for_workers_seconds` elapses. Unreachable endpoints
   are excluded (with a logged reason) instead of hanging the load. Under
   Gen 2 discovery the initial `llama-server` start is *deferred* until
   workers are discovered (or the grace period expires), so the model is not
   loaded solo only to be reloaded seconds later.
2. **Probe ground truth.** `llama-server --list-devices --rpc <endpoints>`
   enumerates the devices exactly as the bundled build will see them —
   names, order, and free/total memory, local and remote. This is the same
   order `--tensor-split` values apply in, so the plan can never disagree
   with llama.cpp about device ordering. If the probe fails, BSDK falls
   back to llama.cpp's default split and says so in diagnostics.
3. **Compute weights.** Per device: `usable = free − reserve` (VRAM vs RAM
   reserve chosen by what actually backs the device — workers advertise the
   devices their rpc-server exposes, parsed from its startup banner). Then:
   - `balanced`: weight = usable memory (pure proportional — never 50/50
     unless capacity actually is equal);
   - `auto`: usable memory × CPU-device discount (default 0.5, because a
     RAM-backed device computes slowly) × latency discount
     (`latency_discount_ms / (latency_discount_ms + rtt)`);
   - `worker_preferred`: `auto` weights, coordinator devices additionally
     scaled by `coordinator_weight_scale` (default 0.2);
   - `manual`: per-node weights from `manual_allocations` (keys are node_id
     or host), split within a node by usable memory. Unlisted nodes get 0.
   Devices below reserves or `minimum_worker_vram_gb` are excluded with a
   recorded reason.
4. **Translate + validate.** Weights become `--tensor-split w1,w2,...` in
   probe order — the only per-device placement control the bundled build
   supports (`-ngl` stays as configured; explicit `inference.tensor_split`
   always wins). If validation fails (all zero, count mismatch), no flag is
   emitted and llama.cpp's default is used, with `fallback_reason` set.
5. **Log everything.** The device list, per-device usable memory, weights,
   estimated shares, exclusions, and the full (secret-redacted) effective
   `llama-server` command are logged and exposed via the API.

## 4. Diagnostics

- `GET /api/v1/distribution` (any node) — policy, per-device allocation
  (with `source: measured|estimated` labels), effective RPC endpoints vs the
  set llama-server was actually launched with, exclusions with reasons,
  topology-stale flag, restart state, redacted effective command, worker
  capabilities (RAM/VRAM/CPU model/GPU/rpc-server devices/readiness).
- `GET /api/v1/cluster` — now embeds the same summary under `distribution`
  for coordinators; the dashboard renders it as the **Model Distribution**
  panel (share bars per device, stale/reload badges, exclusion reasons).
- `GET /health` — per-node `capabilities` (total/available RAM, CPU model +
  cores, GPU backend/model/VRAM, rpc-server readiness and exposed devices).
- Worker GPU truth: the worker parses its own `ggml-rpc-server` startup
  banner, so `capabilities.rpc_devices` reports what the *binary* exposes
  (`["CUDA0"]` vs `["CPU"]`) — catching the "GPU present but CPU-only
  build" mismatch explicitly.

Secrets (cluster token, API keys in `extra_args`) are redacted from logs,
subprocess diagnostics, and API responses. Subprocess output still goes to
log files, never an undrained pipe.

## 5. Topology changes (late joins, departures, pause/resume)

llama.cpp cannot add or remove RPC devices on a loaded model, so BSDK now:

- marks the topology **stale** when the effective endpoint set differs from
  the launched one (visible in diagnostics and the dashboard);
- **debounces** restarts (`restart_debounce_seconds`) so flapping discovery
  cannot restart llama-server in a loop;
- skips the restart while a newly-announced worker's RPC port is still
  unreachable (no restart-to-nowhere loops);
- **waits for active requests and coordinator leases to drain** before
  restarting — never inline from a request handler;
- reports the restart as `pending / running / success / failed`;
- offers `POST /api/v1/inference/reload` for an operator-controlled reload
  (bypasses the debounce, still drains requests first).

## 6. Validation procedure — two Windows PCs

PC-A = coordinator (this machine), PC-B = worker. All commands from
`distributed-ai-os\`.

### 6.1 Confirm the worker binary has the GPU backend

On the machine that builds the worker binaries:

```powershell
.\scripts\windows\build-llama-cpp.ps1 -Cuda -InstallDir .\packaging\windows\bin   # NVIDIA
# or -Vulkan for AMD/Intel/NVIDIA via Vulkan SDK
```

On PC-B, run the rpc-server manually once and read its banner:

```powershell
& "$env:LOCALAPPDATA\BSDK\bin\ggml-rpc-server.exe" --host 127.0.0.1 -p 50053
# GPU build prints e.g.:
#   ggml_cuda_init: found 1 CUDA devices: ...
#   Devices:
#     CUDA0: NVIDIA GeForce RTX 3060 (12288 MiB, 11800 MiB free)
# CPU-only build prints a CPU device and no ggml_cuda_init line.
```

Equivalently, once the worker node is running, check
`Invoke-RestMethod http://<PC-B>:8001/api/v1/distribution` →
`local_capabilities.rpc_devices` should list `CUDA0` (not `CPU`), and
`notes` will call out a CPU-only build on GPU hardware.

### 6.2 Verify ggml-rpc-server detects the worker GPU

Worker log at `%LOCALAPPDATA%\BSDK\logs\` (or `$env:DAIOS_LOG_DIR`):
`<node-id>-rpc-server.log` must contain the `Devices:` banner with the GPU.
`nvidia-smi` on PC-B should show `ggml-rpc-server.exe` holding VRAM once a
model is loaded.

### 6.3 Inspect the coordinator's effective llama-server command

```powershell
Invoke-RestMethod http://<PC-A>:8000/api/v1/distribution | Select-Object -Expand effective_command
```

Also logged at startup as `Effective llama-server command: ...` (secrets
masked). Confirm `--rpc <PC-B>:50052` is present (§6.4) and, with a
distribution policy, `--tensor-split`.

### 6.4 Confirm the worker RPC endpoint is included

`/api/v1/distribution` → `launched_rpc_endpoints` must contain
`<PC-B>:50052`; `excluded_endpoints` must be empty (a reason appears there
otherwise, e.g. firewall blocking TCP 50052).

### 6.5 Monitor RAM and VRAM on both machines

- Both PCs: Task Manager → Performance (RAM, GPU → Dedicated GPU memory),
  or `nvidia-smi -l 2` for VRAM/GPU utilization.
- Continuously via BSDK: `/api/v1/cluster` (`local_resources`, per-peer
  `resources`) and the dashboard Resource panel; `capabilities` adds
  VRAM total/available per node.

### 6.6 Confirm tensors/ops are actually assigned remotely

- Coordinator `llama-server` log (`<node-id>-llama-server.log`): the model
  loader prints per-device buffer sizes, e.g.
  `load_tensors: RPC[<PC-B>:50052] model buffer size = ... MiB`.
  That line is the direct proof of remote tensor storage.
- PC-B VRAM (GPU worker) or RAM (CPU worker) jumps by that amount during
  model load; it drops when llama-server stops.
- During generation, PC-B shows GPU/CPU utilization and steady network
  traffic to port 50052.
- `/api/v1/distribution` shows each device's planned share (estimated,
  labeled as such) next to the measured free/total memory.

### 6.7 Compare performance with and without the worker

Use the built-in benchmark against the coordinator:

```powershell
.venv\Scripts\python.exe benchmarks\run_benchmark.py --base-url http://<PC-A>:8000/v1
```

Record model load time (llama-server log timestamps), prompt-processing
and token-generation speed (llama-server prints `prompt eval time` /
`eval time` per request), plus RAM/VRAM/CPU/GPU on both PCs (§6.5) and
network throughput (Task Manager → Ethernet) for each scenario:

| Scenario | How |
|---|---|
| Coordinator only | worker paused (`POST /api/v1/workers/pause`) or stopped |
| + CPU-only worker | worker running CPU-only rpc-server build |
| + GPU worker | worker running `-Cuda`/`-Vulkan` build |
| worker_preferred | `distribution.policy: worker_preferred`, reload |
| auto (balanced by capability) | `distribution.policy: auto`, reload |

Expected honest outcomes: pooled capacity always increases (bigger models
load); tokens/s *improves* only when worker compute is meaningfully faster
than the coordinator resources it displaces, and *decreases* when a slow
CPU-only worker is given a large share (this is why `auto` discounts
CPU-backed devices).

### 6.8 Identify network or backend bottlenecks

- High RPC latency: `/api/v1/distribution` worker capabilities include
  measured heartbeat RTT; `ping <PC-B>` for baseline. Token generation
  speed dropping with the worker attached + low GPU utilization on both
  ends ⇒ network-bound (each token crosses the LAN per device boundary).
- Worker backend missing: `rpc_devices: ["CPU"]` on GPU hardware ⇒ rebuild
  with `-Cuda`/`-Vulkan` (§6.1).
- Coordinator using local resources despite workers: check
  `fallback_reason` and `excluded_endpoints` in `/api/v1/distribution` —
  every fallback path records why.

## 7. What remains on the coordinator (unavoidable)

Even with `worker_preferred` and all layers offloaded, the coordinator
keeps: the HTTP server and OpenAI proxy, tokenization, the sampling loop
and logits readback for every token, ggml graph scheduling, the GGUF read
during load, any non-offloaded layers (coordinator CPU + RAM), and the
memory-mapped model file pages. Those pages are mapped, not locked: `--mlock`
is passed only for a solo coordinator whose RAM comfortably exceeds the model,
because locking the whole model resident while pooling workers would re-impose
the single-machine memory ceiling `--rpc` exists to escape (and, for a model
larger than local RAM, turns the load into swap thrash that never finishes).
A coordinator therefore always
shows nonzero CPU/RAM activity during inference; the goal of the policy is
to move the *model tensors, KV cache, and per-layer compute* — the bulk of
the footprint — onto workers, not to make the coordinator idle.
