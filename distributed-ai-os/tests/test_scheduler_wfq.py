"""Tests for weighted fair queue and priority behavior."""

from __future__ import annotations

from daios_node.scheduler.wfq import FairQueue, QueueItem
from daios_protocol.config import SchedulerConfig
from daios_protocol.scheduling import Priority


def _item(req: str, tenant: str, prio: Priority, tokens: int = 100) -> QueueItem:
    return QueueItem(request_id=req, tenant_id=tenant, estimated_tokens=tokens, priority=prio)


def test_interactive_priority_is_strict():
    fq = FairQueue(SchedulerConfig())
    fq.push(_item("b1", "t1", Priority.BACKGROUND))
    fq.push(_item("i1", "t1", Priority.INTERACTIVE))
    assert fq.pop_next().request_id == "i1"  # type: ignore[union-attr]
    assert fq.pop_next().request_id == "b1"  # type: ignore[union-attr]


def test_weighted_ratio_is_approximately_4_to_1():
    cfg = SchedulerConfig(
        interactive_weight=4.0,
        background_weight=1.0,
        tenant_weights={"a": 4.0, "b": 1.0},
    )
    fq = FairQueue(cfg)
    for i in range(200):
        fq.push(_item(f"a-{i}", "a", Priority.BACKGROUND))
        fq.push(_item(f"b-{i}", "b", Priority.BACKGROUND))
    served = {"a": 0, "b": 0}
    for _ in range(100):
        item = fq.pop_next()
        assert item is not None
        served[item.tenant_id] += 1

    ratio = served["a"] / max(served["b"], 1)
    assert 2.5 <= ratio <= 5.5


def test_steal_candidate_never_interactive():
    fq = FairQueue(SchedulerConfig())
    fq.push(_item("i1", "t1", Priority.INTERACTIVE))
    fq.push(_item("b1", "t1", Priority.BACKGROUND))
    cand = fq.steal_candidate()
    assert cand is not None
    assert cand.priority != Priority.INTERACTIVE
