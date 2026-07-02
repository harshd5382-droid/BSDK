"""Node API tests for the /api/v1/distribution diagnostics and reload."""

from __future__ import annotations

from fastapi.testclient import TestClient

from daios_node.app import NodeApp
from daios_protocol.config import NodeConfig


def _mock_coordinator(distribution: dict | None = None) -> NodeConfig:
    inference: dict = {"backend": "mock"}
    if distribution is not None:
        inference["distribution"] = distribution
    return NodeConfig.model_validate(
        {
            "node_id": "coord-1",
            "role": "coordinator",
            "inference": inference,
            "peers": [{"id": "w1", "host": "10.0.0.2", "rpc_port": 50052}],
        }
    )


def test_distribution_endpoint_reports_legacy_policy_none():
    app = NodeApp(_mock_coordinator()).create_app()
    with TestClient(app) as client:
        payload = client.get("/api/v1/distribution").json()
    assert payload["policy"] is None
    assert payload["restart_state"] == "idle"
    assert payload["rpc_endpoints"] == ["10.0.0.2:50052"]
    assert payload["topology_stale"] is False
    assert payload["local_capabilities"]["node_id"] == "coord-1"


def test_distribution_endpoint_reports_configured_policy():
    app = NodeApp(_mock_coordinator({"policy": "worker_preferred"})).create_app()
    with TestClient(app) as client:
        payload = client.get("/api/v1/distribution").json()
    assert payload["policy"] == "worker_preferred"


def test_distribution_endpoint_available_on_workers():
    config = NodeConfig.model_validate(
        {"node_id": "w-1", "role": "worker", "inference": {"backend": "mock"}}
    )
    app = NodeApp(config).create_app()
    with TestClient(app) as client:
        payload = client.get("/api/v1/distribution").json()
    assert payload["policy"] is None
    caps = payload["local_capabilities"]
    assert caps["rpc_port"] == 50052
    assert caps["ram_total_gb"] is not None


def test_reload_endpoint_mock_backend_is_noop():
    app = NodeApp(_mock_coordinator()).create_app()
    with TestClient(app) as client:
        payload = client.post("/api/v1/inference/reload").json()
    assert payload["restart_state"] == "idle"


def test_reload_endpoint_404_on_worker():
    config = NodeConfig.model_validate(
        {"node_id": "w-1", "role": "worker", "inference": {"backend": "mock"}}
    )
    app = NodeApp(config).create_app()
    with TestClient(app) as client:
        assert client.post("/api/v1/inference/reload").status_code == 404


def test_cluster_status_omits_distribution_for_mock_backend():
    app = NodeApp(_mock_coordinator()).create_app()
    with TestClient(app) as client:
        payload = client.get("/api/v1/cluster").json()
    assert payload["distribution"] is None


def test_no_secrets_in_distribution_response():
    config = _mock_coordinator()
    config.inference.extra_args = ["--api-key", "hunter2-cluster-secret"]
    config.security.api_token = None
    app = NodeApp(config).create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/distribution")
    assert "hunter2-cluster-secret" not in response.text
