# 18 — Generation 2 Implementation Order

**Status:** Completed (2026-06-30)  
**Maps to:** Phase 2 Part B deliverables

This document records the ordered build sequence used to deliver Generation 2 without breaking Generation 1.

---

## Prerequisites

- Generation 1 validated (`docs/architecture-gen1.md`, 37+ tests green)
- `packages/protocol` stable public types
- `apps/node` FastAPI daemon with llama.cpp integration

---

## Step-by-Step Sequence

### Step 1 — Protocol extensions

**Files:** `packages/protocol/src/daios_protocol/config.py`, `health.py`, `messages.py`

- Add `DiscoveryConfig`, `SecurityConfig`, `MembershipConfig`, `ResourceCapsConfig`
- Add `MemberInfo`, `MembershipView`, `ResourceAdvertisement`, `CoordinatorLease`
- Add `HeartbeatMessage`, `LeaveMessage`, `HeartbeatResponse`
- Extend `NodeConfig.rpc_endpoints(peer_hosts)` for discovery
- All new fields optional → Gen 1 YAML unchanged

**Exit criteria:** `tests/test_config.py` passes; Gen 1 examples load unchanged.

---

### Step 2 — Resource advertisement

**Files:** `apps/node/src/daios_node/resources.py`

- `gather_advertisement()` — CPU, RAM, GPU (best-effort), disk, caps
- `score_peer_for_placement()` — greedy Gen 2 placement
- `should_refuse_work()` — cap enforcement

**Exit criteria:** `tests/test_resources.py` passes.

---

### Step 3 — Discovery service

**Files:** `apps/node/src/daios_node/discovery.py`, `apps/node/pyproject.toml`

- mDNS via optional `zeroconf` dependency
- Service type `_daios._tcp.local.`
- TXT records: `node_id`, `api_port`, `rpc_port`, `role`, `cluster`
- Graceful fallback when zeroconf absent

**Exit criteria:** `tests/test_discovery.py` passes.

---

### Step 4 — Membership gossip

**Files:** `apps/node/src/daios_node/membership.py`

- Heartbeat loop over HTTP `POST /api/v1/internal/heartbeat`
- Failure detector (`failure_timeout`)
- Graceful leave `POST /api/v1/internal/leave`
- Versioned eventually-consistent member map

**Exit criteria:** `tests/test_membership.py` passes.

---

### Step 5 — Ephemeral coordinator

**Files:** `apps/node/src/daios_node/coordinator.py`

- Per-request `CoordinatorLease` registry
- Greedy worker selection from `MembershipView`
- Lease expiry and merge from remote gossip

**Exit criteria:** `tests/test_coordinator.py` passes.

---

### Step 6 — Security basics

**Files:** `apps/node/src/daios_node/security.py`

- Optional API Bearer token middleware for `/v1/*`
- Dev mTLS cert auto-generation (cryptography optional)
- Default: Gen 1 trusted-LAN mode when `security` block absent

**Exit criteria:** Gen 1 configs start without security block.

---

### Step 7 — Wire into FastAPI app

**Files:** `apps/node/src/daios_node/app.py`, `apps/node/src/daios_node/inference.py`

- Lifespan: start discovery + membership when `discovery.enabled`
- Endpoints: `/api/v1/membership`, internal heartbeat/leave
- `/api/v1/cluster` returns `generation: 2` + `membership` when discovery active
- `/v1/chat/completions` creates coordinator lease, updates RPC peers
- `InferenceManager.set_peer_hosts()` restarts llama-server with new `--rpc`

**Exit criteria:** `tests/test_membership_integration.py` passes.

---

### Step 8 — Examples and configuration

**Files:** `examples/two-node-discovered/*.yaml`

- `coordinator-mdns.yaml`, `worker-mdns.yaml`, `hybrid-mdns.yaml`
- All use `discovery.enabled: true`, `cluster_name: daios-home`

**Exit criteria:** `load_config()` succeeds for all three.

---

### Step 9 — Launcher and dashboard

**Files:** `apps/launcher/src/daios_launcher/config_gen.py`, `validation.py`  
**Files:** `apps/dashboard/src/components/ConnectCoordinator.tsx`, `ConnectWorker.tsx`, `TopologyGraph.tsx`, `types.ts`, `App.tsx`

- Wizard "Auto Discovery" toggle
- `StartRequest.discovery_enabled` field
- Topology graph renders multi-member Gen 2 view
- Validation allows coordinator without `peer_host` when discovery enabled

**Exit criteria:** Launcher tests pass; dashboard builds.

---

### Step 10 — Tests and lint

**Files:** `tests/test_*.py`

- 26 new Gen 2 tests added (discovery, membership, resources, coordinator, integration)
- All 63 tests green
- `make lint` clean

---

### Step 11 — Documentation

**Files:** `docs/phase-2-engineering-specification.md`, `docs/phase-2/*.md`, `docs/architecture-gen2.md`, `README.md`

- Master spec + 18 sub-documents
- Gen 2 architecture with mermaid sequences
- README discovery quick start

---

### Step 12 — Deferred Gen 1 benchmarks

**Files:** `benchmarks/run_lan_benchmark.sh`, `run_heterogeneous_benchmark.py`, `run_oversized_model_benchmark.py`, `benchmarks/results/gen1-deferred-status.md`

- Runnable harnesses that skip gracefully without hardware
- Phase 1 goal doc updated to reference harnesses

---

## Migration from Gen 1 to Gen 2

| Action | Command / Config |
|--------|------------------|
| Keep Gen 1 behavior | Omit `discovery` block or set `discovery.enabled: false` |
| Enable Gen 2 | Add `discovery: { enabled: true, cluster_name: daios-home }` |
| Dashboard auto-join | Check "Auto Discovery" in wizard |
| CLI mock cluster | `daios-node -c examples/two-node-discovered/coordinator-mdns.yaml` |

---

## Next Steps (Gen 3+)

1. Custom scheduler service (`node/scheduler/`) — see `07-scheduler-spec.md`
2. libp2p WAN discovery — see `09-networking-spec.md`
3. Multi-user fairness and quotas — Gen 3
4. Native distributed inference — Gen 4 (benchmark-gated)
5. Physical directory migration — see `01-repository-architecture.md`
