"""Recovery and retry behavior tests."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from daios_node.app import NodeApp
from daios_node.coordinator import CoordinatorRegistry
from daios_node.discovery import DiscoveryService
from daios_node.membership import MembershipService
from daios_protocol.config import NodeConfig
from daios_protocol.health import MemberInfo, MemberStatus


def _config(**overrides) -> NodeConfig:
    raw = {
        "node_id": "coord-1",
        "role": "coordinator",
        "inference": {"backend": "llama.cpp", "max_restarts": 2, "auto_restart": True},
        "discovery": {"enabled": True},
        "membership": {"heartbeat_interval": 0.1, "failure_timeout": 1.0},
    }
    raw.update(overrides)
    return NodeConfig.model_validate(raw)


def test_inference_restart_budget_exhaustion(monkeypatch):
    app = NodeApp(_config())
    manager = app.inference
    starts = 0

    def _start() -> None:
        nonlocal starts
        starts += 1

    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(1)"])
    proc.wait(timeout=5)
    assert proc.poll() is not None
    assert manager.llama_server is None
    manager._start_llama_server = _start  # type: ignore[method-assign]

    from daios_node.inference import ManagedProcess

    manager.llama_server = ManagedProcess(name="llama-server", command=["noop"])
    manager.llama_server.process = proc
    monkeypatch.setattr("daios_node.inference.time.sleep", lambda _: None)

    manager.ensure_running()
    manager.ensure_running()
    manager.ensure_running()

    assert starts == 2
    assert manager.llama_server.last_error is not None
    assert "exceeded restart budget" in manager.llama_server.last_error


def test_deferred_start_reports_pending_status():
    """A coordinator that defers llama-server (distribution + discovery, no
    workers yet) must report ``llama_server_pending=True`` so the launcher's
    start gate does not treat the waiting period as a failure."""
    from daios_protocol.config import DistributionConfig

    config = _config(
        inference={
            "backend": "llama.cpp",
            "max_restarts": 2,
            "auto_restart": True,
            "distribution": DistributionConfig(wait_for_workers_seconds=30.0),
        },
    )
    app = NodeApp(config)
    manager = app.inference
    # Simulate the deferral that InferenceManager.start() sets when no RPC
    # endpoints are available yet (discovery has not found workers).
    manager._llama_start_deferred = True
    status = manager.status()
    assert status.llama_server_pending is True

    manager._llama_start_deferred = False
    assert manager.status().llama_server_pending is False


def test_suspect_workers_stay_pooled():
    """A SUSPECT worker (transient heartbeat miss) must remain in the RPC pool
    so a brief blip does not drop it from --rpc and force a model reload."""
    config = _config()
    discovery = DiscoveryService(config)
    registry = CoordinatorRegistry(config)
    membership = MembershipService(config, discovery, registry)

    from daios_protocol.health import MemberInfo, MemberStatus

    alive = MemberInfo(
        node_id="alive-1",
        host="10.0.0.2",
        api_port=8001,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.ALIVE,
        last_seen=datetime.now(timezone.utc),
    )
    suspect = MemberInfo(
        node_id="suspect-1",
        host="10.0.0.3",
        api_port=8002,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.SUSPECT,
        last_seen=datetime.now(timezone.utc) - timedelta(seconds=1.0),
    )
    dead = MemberInfo(
        node_id="dead-1",
        host="10.0.0.4",
        api_port=8003,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.DEAD,
        last_seen=datetime.now(timezone.utc) - timedelta(seconds=10.0),
    )
    membership._members = {"a": alive, "s": suspect, "d": dead}
    hosts = membership.get_alive_worker_hosts()
    assert "10.0.0.2" in hosts
    assert "10.0.0.3" in hosts
    assert "10.0.0.4" not in hosts


@pytest.mark.asyncio
async def test_proxy_retry_recovers_after_connect_errors(monkeypatch):
    app = NodeApp(_config(discovery={"enabled": False}))
    recoveries = 0
    attempts = 0

    def _ensure_running() -> None:
        nonlocal recoveries
        recoveries += 1

    class FakeClient:
        async def request(self, *_args, **_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise httpx.ConnectError("connection refused")
            return httpx.Response(
                200,
                request=httpx.Request("POST", "http://127.0.0.1:8080/v1/chat/completions"),
                content=b'{"ok":true}',
            )

    app._http_client = FakeClient()  # type: ignore[assignment]
    monkeypatch.setattr(app.inference, "ensure_running", _ensure_running)

    response = await app._request_with_recovery(
        "POST",
        "http://127.0.0.1:8080/v1/chat/completions",
        headers={},
        content=b"{}",
    )
    assert response.status_code == 200
    assert attempts == 3
    assert recoveries == 2


def test_membership_partition_transitions_and_dead_exclusion():
    config = _config()
    discovery = DiscoveryService(config)
    registry = CoordinatorRegistry(config)
    membership = MembershipService(config, discovery, registry)

    alive = MemberInfo(
        node_id="alive-1",
        host="10.0.0.2",
        api_port=8001,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.ALIVE,
        last_seen=datetime.now(timezone.utc),
    )
    suspect = MemberInfo(
        node_id="suspect-1",
        host="10.0.0.3",
        api_port=8002,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.ALIVE,
        last_seen=datetime.now(timezone.utc) - timedelta(seconds=0.6),
    )
    dead = MemberInfo(
        node_id="dead-1",
        host="10.0.0.4",
        api_port=8003,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.ALIVE,
        last_seen=datetime.now(timezone.utc) - timedelta(seconds=2.0),
    )

    membership._members = {"a": alive, "s": suspect, "d": dead}
    membership._mark_suspect_dead()

    assert suspect.status == MemberStatus.SUSPECT
    assert dead.status == MemberStatus.DEAD

    endpoints = registry._select_workers([alive, suspect, dead])
    assert "10.0.0.2:50052" in endpoints
    assert "10.0.0.4:50052" not in endpoints


def _worker_member(node_id: str, host: str) -> MemberInfo:
    return MemberInfo(
        node_id=node_id,
        host=host,
        api_port=8001,
        rpc_port=50052,
        role="worker",
        status=MemberStatus.ALIVE,
        last_seen=datetime.now(timezone.utc),
    )


def test_dead_workers_are_evicted_from_the_rpc_pool():
    """Skipping the update on an empty worker list left llama-server pointed at
    RPC endpoints that no longer answer, so every request failed forever."""
    app = NodeApp(_config())
    app.membership._members = {"w1": _worker_member("w1", "10.0.0.2")}
    app._sync_inference_peers()
    assert app.inference.rpc_endpoints_effective() == ["10.0.0.2:50052"]

    app.membership._members["w1"].status = MemberStatus.DEAD
    app._sync_inference_peers()
    assert app.inference.rpc_endpoints_effective() == []


def test_lease_creation_does_not_mutate_the_rpc_topology():
    """Placement scores shift with load; letting them drive set_peer_hosts
    marked the topology stale and reloaded the model mid-conversation."""
    app = NodeApp(_config())
    app.membership._members = {
        "w1": _worker_member("w1", "10.0.0.2"),
        "w2": _worker_member("w2", "10.0.0.3"),
    }
    app._sync_inference_peers()
    before = app.inference.rpc_endpoints_effective()

    view = app.membership.get_membership_view()
    app.coordinator_registry.create_lease([view.members[0]])

    assert app.inference.rpc_endpoints_effective() == before
