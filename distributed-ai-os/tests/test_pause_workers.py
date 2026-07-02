"""Tests for temporarily disconnecting workers from the RPC pool."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from daios_protocol.config import NodeConfig

from daios_node.app import NodeApp
from daios_node.inference import InferenceManager


def _coordinator_config() -> NodeConfig:
    return NodeConfig.model_validate(
        {
            "node_id": "coord-1",
            "role": "coordinator",
            "inference": {"backend": "mock"},
            "peers": [
                {"id": "w1", "host": "10.0.0.2", "rpc_port": 50052},
                {"id": "w2", "host": "10.0.0.3", "rpc_port": 50052},
            ],
        }
    )


@pytest.fixture
def coordinator_client():
    app = NodeApp(_coordinator_config()).create_app()
    with TestClient(app) as client:
        yield client


def test_pause_and_resume_roundtrip(coordinator_client):
    assert coordinator_client.get("/api/v1/workers/paused").json() == {"paused": []}

    resp = coordinator_client.post("/api/v1/workers/pause", json={"host": "10.0.0.2:50052"})
    assert resp.status_code == 200
    assert resp.json() == {"paused": ["10.0.0.2"]}  # port stripped

    resp = coordinator_client.post("/api/v1/workers/resume", json={"host": "10.0.0.2"})
    assert resp.json() == {"paused": []}


def test_pause_rejects_empty_host(coordinator_client):
    resp = coordinator_client.post("/api/v1/workers/pause", json={"host": "  "})
    assert resp.status_code == 400


def test_pause_is_idempotent(coordinator_client):
    for _ in range(2):
        resp = coordinator_client.post("/api/v1/workers/pause", json={"host": "10.0.0.2"})
    assert resp.json() == {"paused": ["10.0.0.2"]}


def test_pause_endpoints_404_on_worker():
    config = NodeConfig.model_validate(
        {"node_id": "w-1", "role": "worker", "inference": {"backend": "mock"}}
    )
    app = NodeApp(config).create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/workers/paused").status_code == 404
        assert client.post("/api/v1/workers/pause", json={"host": "x"}).status_code == 404


def test_inference_excludes_paused_hosts_gen1():
    manager = InferenceManager(_coordinator_config())
    assert manager.rpc_endpoints_effective() == ["10.0.0.2:50052", "10.0.0.3:50052"]
    manager.set_excluded_hosts({"10.0.0.2"})
    assert manager.rpc_endpoints_effective() == ["10.0.0.3:50052"]
    manager.set_excluded_hosts(set())
    assert manager.rpc_endpoints_effective() == ["10.0.0.2:50052", "10.0.0.3:50052"]


def test_inference_excludes_paused_hosts_gen2_discovered():
    manager = InferenceManager(_coordinator_config())
    manager.set_peer_hosts(["10.0.0.7", "10.0.0.8"])  # discovery replaces static peers
    manager.set_excluded_hosts({"10.0.0.7"})
    assert manager.rpc_endpoints_effective() == ["10.0.0.8:50052"]
