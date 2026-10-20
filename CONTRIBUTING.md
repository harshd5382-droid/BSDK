# Contributing to BSDK

Thanks for your interest in BSDK! This project is an early-stage prototype, so every bug report, benchmark,
docs fix and pull request genuinely moves it forward.

By participating you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report bugs.** Open a [bug report](https://github.com/harshd5382-droid/BSDK/issues/new/choose) with your
  OS, roles, config and logs.
- **Share benchmarks.** Results from real multi-machine setups (different GPUs, CPU-only workers, Wi-Fi vs
  Ethernet) are especially valuable. See `distributed-ai-os/benchmarks/`.
- **Improve docs.** Typos, unclear steps, missing troubleshooting entries.
- **Write tests.** Particularly around recovery, membership and allocation edge cases.
- **Build features.** Check open issues first, or open a feature request to discuss larger changes before
  you write code.

Security issues should **not** be filed as public issues. See [SECURITY.md](SECURITY.md).

## Development setup

All commands run from `distributed-ai-os/`.

**Linux / macOS / Git Bash**

```bash
git clone https://github.com/<you>/BSDK.git
cd BSDK/distributed-ai-os
make install        # uv if available, otherwise pip; creates .venv
make test
make lint
```

**Windows (PowerShell)**

```powershell
cd BSDK\distributed-ai-os
.\scripts\windows\install-dev.ps1
.venv\Scripts\python.exe -m pytest tests\ -q
.venv\Scripts\python.exe -m ruff check packages\ apps\node apps\launcher tests\ benchmarks\
```

**Dashboard**

```bash
.venv/bin/daios-launcher --root .        # terminal 1: launcher API on :8090
cd apps/dashboard && npm install && npm run dev   # terminal 2: Vite with hot reload
```

You don't need llama.cpp or a GPU for most work. Use the mock backend (`make run-mock`, or any
`*-mock.yaml` example).

## Project structure at a glance

| Package | Responsibility |
|---|---|
| `packages/protocol` (`daios_protocol`) | Shared config (`NodeConfig`), health models, gossip messages. **Change wire and config shapes here**, not in the apps. |
| `apps/node` (`daios_node`) | The FastAPI peer daemon: inference supervision, allocation, membership, discovery, OpenAI proxy |
| `apps/launcher` (`daios_launcher`) | Control plane: config generation, process management, model downloads, remote workers, Windows installer |
| `apps/dashboard` | React 19 + Vite 6 + Tailwind v4 UI that talks to the launcher API |

The [architecture docs](distributed-ai-os/docs/) and the root [README](README.md#how-it-works) explain how the
pieces fit together.

## Invariants to keep

These have caused real bugs before, so reviewers will check them:

1. **Never pipe subprocess output into an undrained `PIPE`.** `llama-server` deadlocks once the buffer fills
   during model load. Write to a log file (see `DAIOS_LOG_DIR`).
2. **Both the streaming and non-streaming proxy paths must release what they take.** That means calling
   `inference_tracker.end()` and `complete_lease()` in `finally` blocks.
3. **Keep Gen 1 configs working.** YAML with `discovery.enabled: false` and static `peers[]` must keep
   behaving exactly as before.
4. **Role is configuration only.** Don't add code paths that assume a permanent master node.
5. **Treat the cluster token as a secret.** Never log it unredacted.

## Making a change

1. **Fork** the repo and create a branch from `main`: `git checkout -b fix/short-description`.
2. **Make focused commits.** One logical change per PR is much easier to review.
3. **Add or update tests** in `distributed-ai-os/tests/` for any behavior change. Bug fixes should come with a
   test that fails without the fix.
4. **Run the checks locally.** `make lint && make test` must pass, and so must `npm run build` in
   `apps/dashboard` if you touched the UI.
5. **Update the docs** (README, `docs/`, example YAML) when you change behavior, config or commands.
6. **Add an entry** under `Unreleased` in [CHANGELOG.md](CHANGELOG.md).
7. **Open a pull request** and fill in the template. CI runs on Ubuntu and Windows.

### Code style

- Python 3.11+, formatted and linted with **ruff** (line length 100). Use type hints on public functions.
- Match the surrounding code: naming, comment density, and the small-module structure of each package.
- Async code uses `asyncio`. Tests run with `asyncio_mode = "auto"`.
- TypeScript in the dashboard is strict. Keep API types in `apps/dashboard/src/types.ts` in sync with the
  launcher responses.

### Commit messages

Use the imperative mood with a short summary line (≤ 72 characters), then a body explaining *why*:

```
Fix lease leak when streaming proxy fails before first chunk

The stream generator never started, so its finally block did not run.
Release the tracker and lease in the caller when setup raises.
```

## Testing on real hardware

If your change touches inference, allocation or networking, please say in the PR what you tested on: OS,
CPU/GPU, number of machines, link type, model and quantization. If you can, include numbers from
`benchmarks/run_benchmark.py`. Mock-only testing is fine to start with; just say so.

## Releases

Maintainers tag releases as `vX.Y.Z` and attach the Windows `daios-worker.exe` and the llama.cpp RPC binaries
(with SHA-256 checksums matching `packaging/windows/binaries-manifest.json`) to the GitHub release. Built
binaries are not committed to the repository.

## Questions

Open a [discussion or issue](https://github.com/harshd5382-droid/BSDK/issues). There are no silly questions.
Unclear docs are a bug.

Contributions are licensed under the project's [MIT License](LICENSE).
