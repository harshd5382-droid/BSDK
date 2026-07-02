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
