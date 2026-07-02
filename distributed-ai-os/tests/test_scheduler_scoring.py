"""Tests for scheduler scoring helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from daios_node.scheduler.scoring import latency_rank, score_node, vram_fit
from daios_protocol.config import ResourceCapsConfig
from daios_protocol.health import GpuInfo, MemberInfo, MemberStatus, ResourceAdvertisement
from daios_protocol.scheduling import Priority


def _member(node_id: str, host: str, *, cpu: float = 10.0, rtt: float = 5.0) -> MemberInfo:
    ad = ResourceAdvertisement(
        node_id=node_id,
        cpu_percent=cpu,
        cpu_available_cores=6,
        ram_total_gb=16,
        ram_available_gb=12,
        gpu=GpuInfo(name="gpu", vram_total_gb=12, vram_used_gb=2, utilization_percent=20),
        rtt_ms={"coord-1": rtt},
        current_workload=0,
        timestamp=datetime.now(timezone.utc),
    )
    return MemberInfo(
        node_id=node_id,
        host=host,
        api_port=8001,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.ALIVE,
        advertisement=ad,
    )


def test_score_node_penalizes_busy_nodes():
    caps = ResourceCapsConfig()
    fast = _member("w1", "10.0.0.2", cpu=20.0, rtt=2.0)
    slow = _member("w2", "10.0.0.3", cpu=80.0, rtt=30.0)
    assert (
        score_node(fast, coordinator_node_id="coord-1", priority=Priority.INTERACTIVE, caps=caps)
        > score_node(slow, coordinator_node_id="coord-1", priority=Priority.INTERACTIVE, caps=caps)
    )


def test_vram_fit_unknown_passes_and_known_checks():
    member = _member("w1", "10.0.0.2")
    assert vram_fit(member, None) is True
    assert vram_fit(member, 6.0) is True
    assert vram_fit(member, 10.0) is False


def test_latency_rank_slo_signal():
    low = _member("w1", "10.0.0.2", rtt=4.0)
    high = _member("w2", "10.0.0.3", rtt=80.0)
    ordered, met = latency_rank(
        [(high, 50.0), (low, 40.0)],
        slo_ms=100,
        estimated_compute_ms=20,
        coordinator_node_id="coord-1",
    )
    assert ordered[0][0].node_id == "w1"
    assert met is True
