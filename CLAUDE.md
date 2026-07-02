# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**BSDK ("Beyond Single Device Kernel")** is a peer-to-peer distributed AI operating system. The working
codebase is the Generation 1+2 prototype in [`distributed-ai-os/`](distributed-ai-os/) — every command below
runs from that directory, not the repo root. The repo root only holds `README.md`, the `goal/` phase specs
(reference only), and a planning image.

The core idea: pool memory across multiple LAN machines to run a single llama.cpp model larger than any one
machine could hold, exposed behind an OpenAI-compatible API. Every machine runs the *same* `daios-node`
software; **role is configuration-only** (`coordinator`, `worker`, `hybrid`) — there are no permanent masters.

## Commands

All from `distributed-ai-os/`. The Makefile and shell scripts are **bash/POSIX and assume a `.venv/bin` layout**
(Linux/macOS or Git Bash). On native Windows the venv is `.venv/Scripts/` and there is no `make`/`bash` —
use the PowerShell equivalents instead:

- `scripts\windows\install-dev.ps1` ≈ `make install`
- `scripts\windows\run-dashboard.ps1` ≈ `make dashboard`
- `scripts\windows\build-exe.ps1` / `build-llama-cpp.ps1` — worker `.exe` and llama.cpp RPC binaries

Run tests/lint on Windows directly through the venv: `.venv\Scripts\python.exe -m pytest tests\ -q` and
`.venv\Scripts\python.exe -m ruff check packages\ apps\node apps\launcher tests\ benchmarks\`. The full suite
(200+ tests, including recovery, distribution/allocation, and mock-backend integration) passes on Windows.

CI/CD: GitHub Actions is defined at `../.github/workflows/ci.yml` for Ubuntu/Windows Python checks and
dashboard build validation.

```bash
make install                 # uv (preferred) or pip — installs the 3 editable packages + dev deps
make test                    # pytest tests/ -v
make lint                    # ruff check (line-length 100, target py311)
make run-mock                # two-node mock cluster, no llama.cpp needed
make dashboard               # build React UI + serve launcher at http://127.0.0.1:8090
make benchmark               # benchmarks/run_benchmark.py against a running coordinator

# Single test
.venv/bin/pytest tests/test_membership.py -v
.venv/bin/pytest tests/test_proxy.py::test_name -v

# Run a node directly (backend comes from the YAML)
.venv/bin/daios-node -c examples/two-node/coordinator-mock.yaml

# Dashboard dev (hot reload): launcher in one shell, Vite in another
.venv/bin/daios-launcher --root .
cd apps/dashboard && npm run dev
```

`pytest` config (`pyproject.toml`) sets `asyncio_mode = "auto"` and wires `pythonpath` to the three `src/`
roots, so tests import `daios_protocol`/`daios_node`/`daios_launcher` without an install — but `make test`
installs first anyway.

## Architecture

Monorepo of three Python packages plus a React dashboard, installed editable into a shared `.venv`:

- **`packages/protocol/`** (`daios_protocol`) — shared, dependency-light. `config.py` is the spine:
  `NodeConfig` loaded from YAML, with `role` driving the `runs_coordinator` / `runs_rpc_server` /
  `discovery_enabled` properties that gate behavior everywhere else. Also `health.py` (Pydantic response
  models like `ClusterStatus`, `NodeHealth`) and `messages.py` (gossip heartbeat/leave). Change a wire/config
  shape here, not in the apps.
- **`apps/node/`** (`daios_node`) — the FastAPI peer daemon (`daios-node`). `app.py` (`NodeApp`) builds the
  app and owns the request lifecycle; the other modules are the subsystems it composes:
  `inference.py` (`InferenceManager` — spawns/supervises `llama-server` and `ggml-rpc-server` subprocesses,
  gates startup on worker RPC readiness, applies topology changes via debounced safe restarts),
  `allocation.py` (tensor-placement policy for the opt-in `inference.distribution` config: probes devices
  with `llama-server --list-devices`, computes `--tensor-split` weights — see `docs/distributed-inference.md`),
  `coordinator.py` (per-request ephemeral leases), `membership.py` + `discovery.py` (Gen 2 mDNS gossip),
  `mock_backend.py` (fake OpenAI responses when `backend: mock`), `peers.py`/`resources.py`/`model_usage.py`.
- **`apps/launcher/`** (`daios_launcher`) — the one-click control plane (`daios-launcher`) that the dashboard
  talks to. It generates node YAML (`config_gen.py`), starts/stops the node subprocess (`process_manager.py`),
  manages GGUF model downloads (`models_manager.py`, HuggingFace), proxies control of remote worker launchers
  over the LAN (`worker_proxy.py`), and on Windows installs a Task Scheduler autostart job
  (`autostart_windows.py`). `bootstrap.py` is the `daios-worker.exe` entry: it clones/updates the repo, installs
  deps, and launches a worker.
- **`apps/dashboard/`** — React 19 + Vite 6 + Tailwind v4 SPA. Talks to the launcher API (`src/api/`),
  polls status via hooks (`src/hooks/`). Built output is served by the launcher.

### Two request paths (mock vs real)

In `NodeApp.create_app`: if `inference.backend == "mock"` it mounts `mock_router` (synthetic completions, no
binaries). Otherwise, **only a coordinator** mounts the OpenAI proxy (`_mount_openai_proxy`) which forwards
`/v1/*` to the local `llama-server` (default port 8080). The coordinator's `llama-server` is launched with
`--rpc <endpoints>` so it pools the worker's memory over GGML RPC (TCP, default port 50052). Workers run only
`ggml-rpc-server` — they never load the model or serve OpenAI requests.

### Generation 1 vs Generation 2 (set by `discovery.enabled`)

- **Gen 1 (discovery off):** peers are listed statically in YAML (`peers[]`). `rpc_endpoints()` builds the
  `--rpc` list from that static list.
- **Gen 2 (discovery on):** mDNS auto-join (`cluster_name: daios`), gossip membership with heartbeat/failure
  detection, and per-request coordinator leases. Alive worker hosts discovered at runtime replace the static
  `peers[]` for the `--rpc` flag. `/api/v1/membership` and `generation: 2` in `/metrics` appear only here.
  Gen 1 YAML still works unchanged when discovery is off — keep that backward compatibility.

### Key invariants when editing

- **Subprocess output goes to a log file, never an undrained PIPE** (`inference.py`): a PIPE that nothing reads
  deadlocks `llama-server` once the buffer fills during model load. `DAIOS_LOG_DIR` sets the log location;
  `LD_LIBRARY_PATH` must point at the bundled llama.cpp libs for real runs.
- The cluster token (`X-DAIOS-Token`) is a **LAN shared secret** — anyone on the network with it controls
  worker launchers. Optional API bearer token and dev mTLS live in `security.py` (node) and the launcher.
- Inference is tracked via `inference_tracker` (active-request count) and coordinator `leases`; both streaming
  and non-streaming proxy paths must `complete_lease` / `end()` in their `finally` blocks.

## Config examples

`examples/two-node/` holds Gen 1 manual YAML (`*-mock.yaml` for no-binary testing, `*-local.yaml` for loopback
two-node, plus `coordinator.yaml`/`worker.yaml` for real cross-machine). `examples/two-node-discovered/` holds
the Gen 2 mDNS equivalents. These are the canonical references for the `NodeConfig` schema.

## Phase docs

`distributed-ai-os/docs/` has the architecture writeups (`architecture-gen1.md`, `architecture-gen2.md`,
phase specs). `goal/` at the repo root holds Phase 2/3 specs that are **reference only** — not yet implemented.
