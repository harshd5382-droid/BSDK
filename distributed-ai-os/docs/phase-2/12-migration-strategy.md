# 12 — Migration Strategy

**Status:** Gen 1→2 path validated  
**SRS ID:** DAIOS-MIG-012

---

## Purpose

Define backward compatibility, data migration, protocol compatibility, rolling upgrades, rollback, feature flags, version negotiation, and zero-downtime upgrade procedures for each generation transition.

---

## Principles

1. **Opt-in new behavior** — `discovery.enabled: false` preserves Gen 1
2. **Additive schemas** — new config fields have safe defaults
3. **API stability** — OpenAI `/v1/*` unchanged across generations
4. **Rolling upgrades** — mixed-generation clusters supported during transition

---

## Gen 1 → Gen 2

### Backward Compatibility

| Aspect | Gen 1 | Gen 2 | Compatible? |
|---|---|---|---|
| Config `peers:` | Required | Optional | Yes |
| `discovery.enabled` | N/A | `false` = Gen 1 | Yes |
| `/cluster` response | `generation: 1` | `generation: 2` + `membership` | Yes (additive) |
| OpenAI API | Yes | Yes | Yes |
| GGML RPC | Yes | Yes | Yes |

### Migration Steps

1. Upgrade `daios-node` package on all nodes (same binary)
2. On one node, add discovery block:
   ```yaml
   discovery:
     enabled: true
     cluster_name: my-cluster
   ```
3. Repeat for second node; verify `/membership` shows both
4. Remove manual `peers:` when mDNS stable (optional)

### Rollback

Set `discovery.enabled: false` and restore `peers:` YAML. No data loss (no persistent cluster DB).

### Feature Flags

| Flag | Default | Effect |
|---|---|---|
| `discovery.enabled` | `false` | mDNS + gossip |
| `security.mtls_enabled` | `false` | mTLS |
| `security.api_token` | `null` | Bearer auth |

---

## Gen 2 → Gen 3 (Planned)

### Protocol Compatibility

- `HeartbeatMessage` gains optional `scheduler_epoch` field
- Old nodes ignore unknown fields (Pydantic `extra: ignore` on extension models)

### Rolling Upgrade

```mermaid
flowchart LR
    A[Upgrade node 1 scheduler.enabled=true] --> B[Shadow mode: log decisions only]
    B --> C[Upgrade remaining nodes]
    C --> D[Enable scheduler placement cluster-wide]
```

1. Deploy Gen 3 binary with `scheduler.enabled: false` on all nodes
2. Enable scheduler on canary; compare with greedy in logs
3. Enable cluster-wide; monitor fairness metrics
4. Rollback: `scheduler.enabled: false` → greedy placement

### Data Migration

None required. Scheduler queue is ephemeral in-memory.

---

## Gen 3 → Gen 4 (Planned)

### Inference Backend Migration

```yaml
inference:
  backend: llama.cpp    # default
  # backend: daios-native  # after benchmark gate
```

| Phase | Config | Behavior |
|---|---|---|
| Shadow | `llama.cpp` + native dry-run | Compare outputs |
| Canary | `daios-native` on one node | A/B traffic split |
| Full | cluster-wide native | GGML RPC fallback flag |

### API Compatibility

OpenAI responses must match token-for-token within FP tolerance in shadow mode.

### Rollback

Set `inference.backend: llama.cpp`; restart inference subprocess.

---

## Gen 4 → Gen 5 (Planned)

- Desktop app uses same REST API
- Plugins require node restart (Gen 5.0) → hot load (Gen 5.1)
- Federation adds gateway role; non-gateway nodes unchanged

---

## Compatibility Matrix

|  | Gen 1 node | Gen 2 node | Gen 3 node |
|---|---|---|---|
| Gen 1 node | ✓ manual peers | ✓ if discovery off | ✓ |
| Gen 2 node | ✓ | ✓ full | ✓ minus scheduler |
| Gen 3 node | ✓ | ✓ | ✓ full |

---

## Version Negotiation

Clients read `MembershipView.generation` and `ClusterStatus.generation`:

```python
if view.generation >= 2:
    use_membership_api()
else:
    use_legacy_peers()
```

Future: `GET /protocol` returns capability list.

---

## Zero-Downtime Upgrades

**Single node:** Not required — restart acceptable for home/lab.

**Multi-node production (Gen 5 target):**

1. Drain node: stop accepting new leases (Gen 3 `DRAINING` state)
2. Wait for in-flight inference completion
3. Rolling restart per node
4. Cluster maintains quorum of alive members via gossip

---

## Config Migration Tool (Planned)

```bash
daios config migrate --from gen1 --to gen2 --in config.yaml --out config-v2.yaml
```

Adds `discovery:` block while preserving `peers:` as fallback seeds.

---

## Testing Requirements per Migration

| Transition | Required Tests |
|---|---|
| Gen 1→2 | `test_membership_integration.py`, manual peer fallback |
| Gen 2→3 | Fairness regression, greedy fallback |
| Gen 3→4 | Output parity benchmark suite |
| Gen 4→5 | Plugin load/unload, API contract tests |

---

## Acceptance Criteria

- [x] Gen 1 configs work unchanged on Gen 2 binary
- [x] `discovery.enabled` is opt-in
- [x] No mandatory data migration for Gen 2
- [ ] Documented rolling upgrade for Gen 3
- [ ] `daios config migrate` CLI (Gen 3)
