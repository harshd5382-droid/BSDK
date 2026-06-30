"""Tests for Generation 2 ephemeral coordinator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from daios_protocol.config import NodeConfig
from daios_protocol.health import MemberInfo, MemberStatus, ResourceAdvertisement

from daios_node.coordinator import CoordinatorRegistry


def _worker(node_id: str, host: str, ram_gb: float = 16.0) -> MemberInfo:
    return MemberInfo(
        node_id=node_id,
        host=host,
        api_port=8001,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.ALIVE,
        last_seen=datetime.now(timezone.utc),
        advertisement=ResourceAdvertisement(
            node_id=node_id,
            ram_available_gb=ram_gb,
            cpu_percent=20.0,
        ),
    )


def test_create_lease_assigns_workers():
    config = NodeConfig.model_validate({"node_id": "coord-1", "role": "coordinator"})
    registry = CoordinatorRegistry(config)
    members = [
        MemberInfo(
            node_id="coord-1",
            host="127.0.0.1",
            api_port=8000,
            rpc_port=50052,
            role="coordinator",
            status=MemberStatus.ALIVE,
            last_seen=datetime.now(timezone.utc),
        ),
        _worker("w1", "10.0.0.2", 32.0),
        _worker("w2", "10.0.0.3", 8.0),
    ]
    lease = registry.create_lease(members, request_id="req-1")
    assert lease.request_id == "req-1"
    assert lease.coordinator_node_id == "coord-1"
    assert any("10.0.0.2" in ep for ep in lease.worker_endpoints)


def test_lease_expires():
    config = NodeConfig.model_validate({"node_id": "coord-1", "role": "coordinator"})
    registry = CoordinatorRegistry(config)
    members = [_worker("w1", "10.0.0.2")]
    lease = registry.create_lease(members)
    registry._leases[lease.request_id].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert registry.get_lease(lease.request_id) is None


def test_multiple_leases_no_conflict():
    config = NodeConfig.model_validate({"node_id": "coord-1", "role": "coordinator"})
    registry = CoordinatorRegistry(config)
    members = [_worker("w1", "10.0.0.2")]
    l1 = registry.create_lease(members, request_id="r1")
    l2 = registry.create_lease(members, request_id="r2")
    assert l1.request_id != l2.request_id
    assert len(registry.active_leases()) == 2


def test_complete_lease_removes():
    config = NodeConfig.model_validate({"node_id": "coord-1", "role": "coordinator"})
    registry = CoordinatorRegistry(config)
    members = [_worker("w1", "10.0.0.2")]
    registry.create_lease(members, request_id="r1")
    registry.complete_lease("r1")
    assert registry.get_lease("r1") is None
    assert len(registry.active_leases()) == 0
