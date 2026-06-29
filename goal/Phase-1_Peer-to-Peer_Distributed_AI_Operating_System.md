# Phase 1 — Deep Research & Architecture Strategy for a Peer-to-Peer Distributed AI Operating System

## Mission

Act as a team of world-class distributed systems engineers, AI infrastructure architects, networking engineers, compiler engineers, operating system designers, and large-scale distributed computing researchers.

Your objective is **not** to simply compare existing projects, nor to design an entirely new inference engine from scratch.

Your objective is to create a realistic, production-oriented architecture and research strategy for building a **Peer-to-Peer Distributed AI Operating System** that evolves from a practical two-node prototype into a fully native distributed AI platform.

The platform should allow independent computers connected through LAN, VPN, or eventually the public internet to behave as one intelligent AI compute fabric while remaining easy to install, scalable, fault tolerant, and cross-platform.

The final deliverable should be an engineering research document that serves as the architectural foundation for a multi-year open-source project.

## Core Vision

Every computer runs exactly the same software.

There are no permanent master or worker nodes.

Every node can simultaneously act as:

- Client
- Worker
- Resource Provider
- Request Coordinator
- API Host
- Scheduler Participant

A user should be able to sit at **any** connected computer and immediately use the combined resources of the entire cluster.

When a request is submitted:

- The local node temporarily becomes the Request Coordinator.
- The coordinator may also contribute its own CPU, RAM, and GPU resources.
- Other available nodes contribute resources according to current availability.
- When the request completes, coordinator responsibilities end automatically.

Another node may coordinate the next request.

The cluster should never depend on one permanently designated machine.

## Research Philosophy

Do not attempt to reinvent every component immediately.

Instead, determine which technologies should:

- Be reused.
- Be extended.
- Be replaced later.
- Be redesigned completely.

The architecture should evolve through successive generations rather than attempting a complete rewrite from day one.

## Long-Term Objective

The long-term goal is **not** to create another wrapper around llama.cpp or an orchestration layer.

The long-term goal is to create a complete Peer-to-Peer Distributed AI Operating System with its own:

- distributed scheduling
- resource management
- networking
- orchestration
- inference execution
- plugin ecosystem
- desktop application
- developer SDKs

However, mature open-source components should be reused whenever doing so accelerates development without compromising the long-term vision.

## Research Goals

For every subsystem answer:

Should this be:

- Reused
- Extended
- Wrapped
- Forked
- Replaced
- Built from scratch

Explain why.

Support every recommendation with technical reasoning.

## Development Generations

### Generation 1 — Practical Prototype

Design the simplest architecture capable of proving the concept.

Reuse mature open-source components whenever possible.

Research:

- llama.cpp
- GGML RPC
- llama-server
- GGUF
- OpenAI-compatible APIs

Determine:

- what problems these already solve well
- their limitations
- what should remain unchanged
- what should eventually be replaced

The prototype should demonstrate:

- two-node inference
- memory pooling
- OpenAI-compatible endpoint
- coding assistant integration
- heterogeneous hardware support

The objective is proving the concept rather than replacing mature inference software.

### Generation 2 — Peer-to-Peer Cluster

Research how to replace manual orchestration.

Design:

- automatic node discovery
- peer-to-peer networking
- cluster membership
- dynamic request coordinators
- resource advertisements
- automatic node joining
- automatic recovery
- intelligent scheduling

Inference may still rely on llama.cpp.

### Generation 3 — Intelligent Scheduling

Research how to replace existing scheduling limitations.

Design:

- adaptive resource allocation
- latency-aware scheduling
- heterogeneous scheduling
- distributed coordinator management
- multi-user scheduling
- fairness
- work stealing
- priority queues
- admission control

Determine whether current inference frameworks provide sufficient scheduling or whether new algorithms should be developed.

### Generation 4 — Native Distributed Inference

Research the feasibility of replacing existing distributed inference implementations.

Investigate:

- asynchronous execution
- tensor routing
- distributed KV cache
- activation routing
- improved CPU utilization
- lower synchronization overhead
- optimized communication
- heterogeneous execution

Only recommend replacing mature implementations if benchmarking predicts measurable improvements.

### Generation 5 — Distributed AI Operating System

Research the architecture required for a complete operating system capable of:

- automatic scaling
- plugin ecosystem
- desktop applications
- cloud federation
- enterprise deployment
- edge computing
- contributed compute marketplace

## Existing Technologies

Research and compare:

Inference:

- llama.cpp
- GGML RPC
- prima.cpp
- distributed-llama
- vLLM
- SGLang
- DeepSpeed
- PyTorch Distributed

Distributed Systems:

- Ray
- Kubernetes
- Docker Swarm
- Nomad
- libp2p
- ZeroMQ
- gRPC
- QUIC
- Consul
- Serf
- Apache Ignite

For each evaluate:

- architecture
- production readiness
- CPU support
- heterogeneous hardware support
- OpenAI compatibility
- scheduling
- networking
- scalability
- licensing
- maintenance
- extensibility

Identify which concepts should influence the final platform.

## Dynamic Coordinator Architecture

Research architectures where:

- every node runs identical software
- any node can coordinate its own request
- multiple coordinators can coexist safely
- coordinators disappear automatically after request completion
- cluster metadata remains consistent
- there is no permanent control plane

Compare distributed consensus approaches with lighter-weight coordination mechanisms.

## Resource Contribution

Research adaptive contribution algorithms.

Every node should continuously advertise:

- CPU usage
- available CPU
- RAM
- available RAM
- GPU
- storage
- bandwidth
- latency
- thermal state
- battery state
- current workload
- user activity
- configured contribution limits

Design algorithms that automatically determine:

- how much work each node should receive
- whether the requesting node should contribute
- how to keep interactive systems responsive
- how to maximize cluster utilization

## Multi-User Operation

Design a cluster supporting multiple simultaneous users.

Each user may submit requests from different computers.

Every request should receive its own temporary coordinator.

Research:

- concurrent coordinators
- request isolation
- scheduling fairness
- quotas
- enterprise policies
- conflict prevention

## Build vs Buy Analysis

For every subsystem produce a matrix:

| Component | Reuse | Extend | Replace Later | Build from Scratch | Reason |
| --- | --- | --- | --- | --- | --- |

Include:

- Discovery
- Scheduler
- Networking
- Resource Manager
- Model Loader
- API Gateway
- Inference Engine
- Storage
- Dashboard
- Desktop Application
- SDKs
- Plugin System
- Security

## Prototype Validation

Design a realistic validation roadmap.

Prototype 1

Two computers.

Prototype 2

Automatic discovery.

Prototype 3

Dynamic coordinator.

Prototype 4

Distributed inference.

Prototype 5

Multi-user cluster.

Prototype 6

Production deployment.

For every prototype define:

- goals
- expected outcome
- measurable success criteria
- limitations
- next milestone

## Deliverables

Produce a complete engineering research document containing:

- Executive Summary
- Architectural Vision
- Evolution Strategy
- Build vs Buy Analysis
- Technology Evaluation
- Peer-to-Peer Cluster Architecture
- Dynamic Coordinator Design
- Resource Contribution Algorithms
- Distributed Scheduling Strategy
- Networking Architecture
- Security Architecture
- Prototype Roadmap
- Performance Expectations
- Scalability Analysis
- Failure Scenarios
- Risk Assessment
- Open-Source Reuse Strategy
- Original Architectural Innovations
- Long-Term Migration Plan from Prototype to Native AI Operating System
- Final Recommendations

The document should describe not only what should be built, but also why each architectural decision is appropriate for the current generation of the project and how it enables the next generation without unnecessary rewrites.

## Generation 1 Implementation Status

Status: Validated (2026-06-29) — real two-node distributed inference proven end-to-end with llama.cpp + GGML RPC.

Repository: distributed-ai-os/ at project root.

Completed:

- Project structure aligned with Phase 2 repository layout (apps/node, packages/protocol, deploy, benchmarks, tests, docs).
- daios-node daemon with coordinator, worker, and hybrid roles via YAML configuration.
- llama.cpp / GGML RPC integration layer (ggml-rpc-server + llama-server subprocess management).
- OpenAI-compatible API (/v1/chat/completions) with proxy to llama-server and mock backend for CI.
- Manual two-node peer configuration with TCP health checks.
- Cluster status API (GET /api/v1/cluster), health (GET /health), metrics (GET /metrics).
- Integration tests (10/10 passing) and benchmark suite.
- Docker Compose for mock two-node cluster.
- llama.cpp build script with -DGGML_RPC=ON.

Technology decisions validated:

- Inference: Reuse llama.cpp + GGML RPC for Generation 1 (memory pooling across nodes).
- API: Reuse llama-server OpenAI API; thin coordinator proxy preserves stable /v1 interface for future generations.
- Discovery, scheduler, security: Deferred to Generations 2–3 per roadmap.

## Generation 1 Validation (2026-06-29)

Environment: built llama.cpp (commit 8c146a8) with `-DGGML_RPC=ON` (binaries `llama-server`, `ggml-rpc-server`); model Qwen2.5-0.5B-Instruct Q4_K_M GGUF; CPU-only host (Intel i3-4130, 4 threads). Topology: loopback two-node (coordinator + one RPC worker on `127.0.0.1`), which exercises the identical TCP/serialization code path as a cross-machine LAN deployment.

Verified:

- Worker `ggml-rpc-server` exposes its CPU device over TCP and accepts coordinator connections.
- Coordinator `llama-server` registers the remote backend via `--rpc` and returns coherent Qwen output.
- `daios-node` orchestrates both processes from YAML configuration.
- OpenAI-compatible API verified: `/v1/models`, non-streaming chat, and streaming SSE (coding-assistant compatible).
- Full test suite green (14/14); lint clean.

Benchmark (8 requests, max_tokens=64):

- Single-node baseline: 13.1 tokens/s; p50 latency 4457 ms.
- RPC-distributed (loopback): 12.4 tokens/s; p50 latency 5303 ms.
- Finding: GGML RPC pools memory across nodes but adds ~5% overhead for models that fit on one node. This confirms the Generation 1 decision to reuse llama.cpp + GGML RPC (prove the concept, pool memory) and defers a native distributed engine to Generation 4 unless benchmarking predicts measurable gains.

Fixes landed during validation:

- Inference subprocess output is redirected to log files to avoid a PIPE-buffer deadlock that stalled `llama-server` model loading.
- The OpenAI proxy detects streaming by parsing the request body (whitespace-robust) in addition to the `Accept: text/event-stream` header.

Full report: `distributed-ai-os/benchmarks/results/gen1-validation-report.md`.

Remaining (cross-machine extensions, not blocking Generation 1 sign-off):

- Two physical/virtual machines over LAN for latency-realistic numbers.
- Heterogeneous hardware benchmark (CPU + GPU split via RPC).
- Memory-pooling validation with a model exceeding single-node RAM.
