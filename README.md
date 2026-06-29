# BSDK — Peer-to-Peer Distributed AI Operating System

Generation 1 prototype implementation lives in [`distributed-ai-os/`](distributed-ai-os/).

## Phase Status

| Phase | Status | Document |
|-------|--------|----------|
| Phase 1 | **Active** | `goal/Phase-1_Peer-to-Peer_Distributed_AI_Operating_System.md` |
| Phase 2 | Reference only | `goal/Phase_2_Engineering_Specification.md` |
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
