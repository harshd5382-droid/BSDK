# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

No version has been tagged yet. This section covers everything in the first public prototype (Generation 1 +
Generation 2) and will become `0.1.0` when it is tagged.

### Added
- **Generation 1:** two-node memory pooling with llama.cpp `llama-server` + `ggml-rpc-server`, an
  OpenAI-compatible proxy, static YAML peers, health and cluster status APIs, and a benchmark suite.
- **Generation 2:** mDNS auto-discovery, gossip membership with heartbeat and failure detection, resource
  advertisements, and ephemeral per-request coordinator leases.
- Resource-aware distributed inference: device probing and generated `--tensor-split` policies (`auto`,
  `balanced`, `worker_preferred`, `manual`), GPU layer offloading for distributed coordinators, and safe
  debounced restarts on topology change.
- Coordinator setup with multiple worker IPs.
- Worker pause and resume, exposed through the node API and the launcher.
- Observability: request latency, failure and token tracking, and a `/metrics/prometheus` endpoint.
- Bounded retry for transient proxy failures while dropped workers are evicted.
- `daios-launcher` control plane with the React dashboard, GGUF model manager (Hugging Face downloads),
  remote worker control, and built-in chat.
- Self-contained Windows worker installer (`daios-worker.exe`): system checks, per-user install, Task
  Scheduler autostart, SHA-256-verified binaries, firewall automation and atomic self-update.
- GitHub Actions CI: lint and tests on Ubuntu and Windows, plus a dashboard build.
- Open-source project files: `LICENSE` (MIT), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, issue
  and PR templates, Dependabot config, `.editorconfig`, and a detailed root README.

### Fixed
- Distributed model loads no longer hang: `--mlock` is applied only to solo coordinators with enough RAM, the
  solo context window is sized from available memory, and model loading runs off the API startup path so
  `/health` answers during the load.
- Dead workers are evicted from the RPC pool, and Gen 2 honours each worker's advertised `rpc_port`.
- Per-request leases no longer trigger mid-conversation model reloads.
- CI no longer fails while installing the root dev package. Setuptools' flat-layout auto-discovery is now
  disabled for it.
- The Ruff rule set is pinned explicitly, so newer Ruff releases with broader defaults no longer break CI.

### Removed
- The prebuilt `daios-worker.exe` and the TypeScript build cache are no longer tracked in git. Release
  binaries will be published through GitHub Releases instead.

[Unreleased]: https://github.com/harshd5382-droid/BSDK/commits/main
