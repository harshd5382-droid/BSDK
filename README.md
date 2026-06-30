# BSDK — Beyond Single Device Kernel

Generation 1 prototype implementation lives in [`distributed-ai-os/`](distributed-ai-os/).

## Phase Status

| Phase | Status | Document |
|-------|--------|----------|
| Phase 1 | **Complete** | `distributed-ai-os/docs/phase-1-research-architecture.md` |
| Phase 2 | **Complete** (spec; Gen 2 implemented, Gen 3–5 specified) | `distributed-ai-os/docs/phase-2-engineering-specification.md` |
| Phase 3 | Reference only | `goal/Phase_3_Autonomous_Engineering_Program.md` |

## Quick Start

```bash
cd distributed-ai-os
make dashboard    # one-click UI — recommended
```

Or for terminal-only mock testing:

```bash
cd distributed-ai-os
make install && make run-mock
```

See [distributed-ai-os/README.md](distributed-ai-os/README.md) for full setup including dashboard, llama.cpp + GGML RPC two-node deployment.
