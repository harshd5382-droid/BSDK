"""Tests for Generation 2 membership gossip."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from daios_protocol.config import NodeConfig
from daios_protocol.health import MemberInfo, MemberStatus
from daios_protocol.messages import HeartbeatMessage, LeaveMessage

from daios_node.coordinator import CoordinatorRegistry
from daios_node.discovery import DiscoveryService
from daios_node.membership import MembershipService


def _member(node_id: str, host: str = "10.0.0.2") -> MemberInfo:
    return MemberInfo(
        node_id=node_id,
        host=host,
        api_port=8001,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.ALIVE,
        last_seen=datetime.now(timezone.utc),
    )


@pytest.fixture
def membership():
    config = NodeConfig.model_validate(
        {
            "node_id": "coord-1",
            "role": "coordinator",
            "discovery": {"enabled": True},
            "membership": {"heartbeat_interval": 0.1, "failure_timeout": 0.5},
        }
    )
    discovery = DiscoveryService(config)
    registry = CoordinatorRegistry(config)
    return MembershipService(config, discovery, registry)


@pytest.mark.asyncio
async def test_handle_heartbeat_upserts_member(membership):
    peer = _member("worker-1")
    msg = HeartbeatMessage(sender=peer, membership_version=1)
    resp = await membership.handle_heartbeat(msg)
    assert resp.sender.node_id == "coord-1"
    assert "worker-1" in membership._members


@pytest.mark.asyncio
async def test_handle_leave_removes_member(membership):
    membership._members["worker-1"] = _member("worker-1")
    await membership.handle_leave(LeaveMessage(node_id="worker-1", membership_version=2))
    assert "worker-1" not in membership._members


def test_mark_suspect_dead(membership):
    old = _member("worker-1")
    old.last_seen = datetime.now(timezone.utc) - timedelta(seconds=20)
    membership._members["worker-1"] = old
    membership._mark_suspect_dead()
    assert membership._members["worker-1"].status == MemberStatus.DEAD


def test_get_membership_view_includes_local(membership):
    view = membership.get_membership_view()
    assert view.local_node_id == "coord-1"
    assert any(m.node_id == "coord-1" for m in view.members)
    assert view.generation == 2


def test_get_alive_worker_hosts(membership):
    membership._members["w1"] = _member("w1", "10.0.0.2")
    membership._members["w2"] = _member("w2", "10.0.0.3")
    hosts = membership.get_alive_worker_hosts()
    assert "10.0.0.2" in hosts
    assert "10.0.0.3" in hosts


def test_get_alive_worker_endpoints_carries_each_workers_own_port(membership):
    worker = _member("w1", "10.0.0.2")
    worker.rpc_port = 60000
    membership._upsert_member(worker)
    membership._upsert_member(_member("w2", "10.0.0.3"))

    assert sorted(membership.get_alive_worker_endpoints()) == [
        "10.0.0.2:60000",
        "10.0.0.3:50052",
    ]


def test_heartbeat_payload_is_built_once_per_round(membership):
    """The gossip payload is identical for every peer; sampling CPU/RAM/disk
    once per peer made heartbeat cost scale with cluster size."""
    membership._upsert_member(_member("w1", "10.0.0.2"))
    membership._upsert_member(_member("w2", "10.0.0.3"))

    msg = membership._build_heartbeat()
    assert msg.sender.node_id == "coord-1"
    assert msg.advertisement is not None
    assert msg.advertisement is msg.sender.advertisement
