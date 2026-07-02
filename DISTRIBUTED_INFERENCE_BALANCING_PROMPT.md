# BSDK Distributed Inference Resource Balancing

## Task

Improve distributed inference in **BSDK (Beyond Single Device Kernel)**. Perform all implementation and validation work from the `distributed-ai-os/` directory.

## Problem

When the main PC runs as the BSDK coordinator and another PC joins as a worker, inference does not use the machines as expected.

The coordinator consumes most of the available resources:

- High CPU usage
- High GPU usage
- High system RAM usage
- High GPU VRAM usage

Meanwhile, the worker contributes much less:

- Low CPU and GPU utilization
- Only a small amount of system RAM or GPU VRAM is used
- Little inference work appears to be executed remotely
- Adding the worker provides limited improvement in model capacity or inference speed

The intended behavior is for BSDK to use the useful resources of both machines. The worker should contribute its available system RAM, GPU VRAM, and supported compute capacity instead of leaving most of the workload on the coordinator.

## Important technical distinction

Do not assume that llama.cpp GGML RPC provides perfectly symmetrical distributed inference.

First determine exactly what GGML RPC and the bundled llama.cpp version can distribute:

- Model tensor storage
- Tensor operations
- CPU computation
- GPU computation
- GPU VRAM
- System RAM
- KV cache
- Prompt processing
- Token generation
- Sampling
- Model loading
- Backend initialization

Some work may necessarily remain on the coordinator, including orchestration, sampling, context or KV-cache storage, and parts of the computation graph. Clearly document these limitations.

Do not claim that system RAM, GPU VRAM, or compute has been pooled unless runtime evidence confirms it. System RAM and GPU VRAM are separate resources and must not be described as interchangeable.

## Objective

Investigate why the coordinator performs most of the work and implement the best practical resource-distribution strategy supported by llama.cpp and GGML RPC.

The solution should:

1. Use worker RAM and VRAM for model tensors whenever supported.
2. Offload eligible computation to worker CPUs or GPUs.
3. Prevent the coordinator from receiving an unnecessarily large portion of the model.
4. Account for machines with different hardware capabilities.
5. Expose enough diagnostics to prove where memory and computation are occurring.
6. Preserve compatibility with existing Generation 1 and Generation 2 configurations.

## Investigation requirements

Trace the complete real-backend startup path, including:

- Node configuration loading
- Worker discovery or static peer selection
- RPC endpoint generation
- `ggml-rpc-server` startup
- `llama-server` startup
- Construction of the `--rpc` argument
- GPU-layer configuration
- Tensor placement and split configuration
- Environment variables and backend-library loading
- Worker capability and resource reporting

Inspect the exact commands used to start:

- The coordinator's `llama-server`
- Every worker's `ggml-rpc-server`

Log these commands safely without exposing secrets.

Determine whether the behavior is caused by one or more of the following:

- Incorrect or incomplete llama.cpp RPC flags
- Local devices being preferred over RPC devices
- Missing tensor-split configuration
- Incorrect device ordering
- Conservative or hard-coded GPU-layer settings
- Worker GPU backends not being detected
- RPC workers running CPU-only binaries
- CUDA, Vulkan, or other acceleration libraries not loading
- Stale or incompatible llama.cpp binaries
- Workers reporting inaccurate RAM or VRAM capacity
- The coordinator starting before workers are ready
- Discovered nodes not being included in `--rpc`
- The model being loaded before a worker joins
- No restart or reload after the worker topology changes
- Network latency making remote execution inefficient
- Context or KV-cache allocations remaining local
- Fundamental llama.cpp or GGML RPC architectural limitations

## Capability reporting

Extend node resource reporting so BSDK can distinguish between:

- Total and available system RAM
- CPU model and logical-core count
- GPU backend
- GPU model
- Total and available GPU VRAM
- RPC server readiness
- Supported llama.cpp devices and backends
- Whether a worker is CPU-only or GPU-enabled
- RPC address and port
- Relevant network information, such as measured latency when practical

Handle missing GPU support and unavailable metrics gracefully.

## Resource-allocation policy

Implement a configurable allocation policy for real llama.cpp inference.

At minimum, support:

- `auto`: allocate tensors based on usable RAM, VRAM, network conditions, and device capabilities.
- `balanced`: aim for proportional utilization across eligible nodes.
- `worker_preferred`: place as much eligible model data and computation as possible on workers while keeping coordinator use lower.
- `manual`: allow explicit per-device or per-node allocation values.

The default must remain backward-compatible. Existing YAML files must continue to work without modification.

A possible configuration shape is:

```yaml
inference:
  backend: llama_cpp
  model_path: models/example.gguf

  distribution:
    policy: auto
    coordinator_reserve_ram_gb: 4
    coordinator_reserve_vram_gb: 1
    worker_reserve_ram_gb: 2
    worker_reserve_vram_gb: 0.5
    minimum_worker_vram_gb: 1
    prefer_worker_devices: true

    manual_allocations:
      worker-node-1:
        weight: 0.7
      coordinator-node:
        weight: 0.3
```

This schema is only a suggestion. Adapt it to the existing `NodeConfig` design and the controls actually supported by the bundled llama.cpp build.

Never generate command-line flags that the bundled llama.cpp version does not support.

## Allocation calculation

For automatic allocation:

1. Discover all ready RPC workers before starting `llama-server`.
2. Collect their available system RAM, GPU VRAM, and backend capabilities.
3. Reserve configurable memory for the operating system and other processes.
4. Estimate usable capacity for every eligible device.
5. Calculate allocation weights proportional to usable capacity.
6. Incorporate network latency or throughput when it materially affects remote execution.
7. Translate the weights into controls supported by the bundled llama.cpp build.
8. Validate the generated allocation before launching inference.
9. Log the resulting device list, weights, and estimated placement.
10. Fall back safely if a worker is unavailable or incompatible.

Do not assume equal splits. For example, a worker with 8 GB of usable VRAM should not receive the same allocation as one with 24 GB unless explicitly configured.

A slow worker should not automatically receive a large compute allocation merely because it has significant memory.

## Lifecycle and topology changes

Handle workers that join after the coordinator has already loaded the model.

Determine whether llama.cpp supports dynamically adding RPC devices. If it does not:

- Clearly expose that limitation.
- Mark the model topology as stale.
- Provide a controlled model reload or inference restart operation.
- Avoid interrupting active requests.
- Wait for active inference and coordinator leases to finish.
- Restart `llama-server` with the updated RPC device list.
- Report whether a restart is pending, running, successful, or failed.

Do not restart inference repeatedly because of unstable discovery events. Add suitable stabilization or debounce behavior.

## Diagnostics and observability

Add diagnostics that make the distribution observable.

Expose, where technically possible:

- Coordinator system RAM usage
- Coordinator GPU VRAM usage
- Per-worker system RAM usage
- Per-worker GPU VRAM usage
- Per-node CPU utilization
- Per-node GPU utilization
- Model tensor allocation by device and node
- RPC bytes sent and received
- RPC request or operation counts
- RPC latency
- Worker readiness
- Worker backend and device detection
- Effective llama.cpp launch flags
- Active inference requests
- Current distribution policy
- Whether the topology requires a model reload

Add these details to an appropriate status or diagnostics endpoint and display the most useful values in the dashboard.

Clearly label estimated values separately from directly measured values.

## Logging and error handling

Improve logs so an operator can answer:

- Which workers were discovered?
- Which RPC endpoints were passed to llama.cpp?
- Which GPUs and backends were detected?
- How much usable RAM and VRAM was reported?
- What allocation was calculated?
- Which tensors or model layers were placed remotely?
- Why was a worker excluded?
- Did the worker binary contain GPU support?
- Did the RPC connection fail?
- Is the coordinator using local resources because of an RPC limitation?

Preserve the existing invariant that subprocess output goes to log files and never to an undrained pipe.

Never expose cluster tokens, bearer tokens, or other secrets in logs, subprocess command diagnostics, or API responses.

## Compatibility requirements

Preserve:

- Generation 1 static-peer configurations
- Generation 2 discovery-based configurations
- Mock backend behavior
- Coordinator, worker, and hybrid roles
- Existing configuration files
- Existing OpenAI-compatible endpoints
- Streaming and non-streaming request cleanup
- Lease and inference-tracker cleanup
- Windows support
- Linux and macOS behavior

All commands must be executed from `distributed-ai-os/`.

On Windows, use:

```powershell
.venv\Scripts\python.exe -m pytest tests\ -q
.venv\Scripts\python.exe -m ruff check packages\ apps\node apps\launcher tests\ benchmarks\
```

## Testing requirements

Add unit and integration tests for:

- Allocation between equal-capacity nodes
- Allocation between unequal-capacity nodes
- Worker-preferred allocation
- Manual allocation
- CPU-only workers
- GPU-enabled workers
- Workers with insufficient available memory
- Unreachable RPC workers
- Late worker discovery
- Worker departure
- Stale-topology detection
- Safe inference restart
- Generation 1 static peers
- Generation 2 discovered peers
- Mock backend compatibility
- Invalid configuration
- Unsupported llama.cpp flags
- Missing resource metrics
- Protection of secrets in logs and diagnostics

Mock hardware and subprocess behavior where physical GPUs or multiple machines are unavailable.

## Validation on real machines

Provide a repeatable validation procedure for two Windows PCs.

The procedure should show:

1. How to confirm that the worker binary has the required GPU backend.
2. How to verify that `ggml-rpc-server` detects the worker GPU.
3. How to inspect the coordinator's effective `llama-server` command.
4. How to confirm the worker RPC endpoint is included.
5. How to monitor system RAM and GPU VRAM on both machines.
6. How to confirm that tensors or operations are actually assigned remotely.
7. How to compare inference performance with and without the worker.
8. How to identify network or backend bottlenecks.

Compare at least these scenarios:

- Coordinator only
- Coordinator plus a CPU-only worker
- Coordinator plus a GPU worker
- Worker-preferred distribution
- Automatic balanced distribution

Record:

- Model load time
- Prompt-processing speed
- Token-generation speed
- Coordinator RAM and VRAM usage
- Worker RAM and VRAM usage
- Coordinator CPU and GPU usage
- Worker CPU and GPU usage
- RPC traffic and latency

## Acceptance criteria

The task is complete when:

- The root cause of coordinator-heavy behavior is identified with evidence.
- BSDK correctly discovers and validates eligible RPC devices.
- The generated llama.cpp configuration uses supported distribution controls.
- Worker resources are used proportionally when technically supported.
- Operators can see per-node allocation and utilization.
- Unequal hardware is handled without assuming a 50/50 split.
- Late worker joins are handled explicitly and safely.
- Existing Gen 1, Gen 2, and mock configurations remain functional.
- Tests and lint pass.
- Documentation clearly distinguishes distributed compute from distributed tensor storage.
- Any unavoidable coordinator CPU, RAM, GPU, VRAM, KV-cache, or sampling work is documented honestly.

Do not merely reduce coordinator usage by applying arbitrary limits. Diagnose the actual tensor placement, backend capabilities, RPC behavior, and llama.cpp constraints, then implement the most effective supported solution.
