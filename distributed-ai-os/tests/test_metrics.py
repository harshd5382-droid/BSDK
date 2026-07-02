"""Tests for inference metrics tracking and the metrics endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from daios_node.app import NodeApp
from daios_node.inference_tracker import InferenceTracker
from daios_protocol.config import NodeConfig


def test_tracker_accounting():
    t = InferenceTracker()
    assert t.snapshot()["total_requests"] == 0
    start = t.begin()
    assert t.active == 1
    t.end(start, tokens=42)
    snap = t.snapshot()
    assert snap["active_requests"] == 0
    assert snap["total_requests"] == 1
    assert snap["total_tokens"] == 42
    assert snap["failed_requests"] == 0
    assert snap["last_latency_ms"] >= 0.0


def test_tracker_counts_failures():
    t = InferenceTracker()
    t.end(t.begin(), failed=True)
    snap = t.snapshot()
    assert snap["total_requests"] == 1
    assert snap["failed_requests"] == 1


def _mock_node() -> NodeApp:
    cfg = NodeConfig.model_validate(
        {"node_id": "metrics-node", "role": "coordinator", "inference": {"backend": "mock"}}
    )
    return NodeApp(cfg)


def test_metrics_endpoint_includes_request_snapshot():
    node = _mock_node()
    node.inference_tracker.end(node.inference_tracker.begin(), tokens=10)
    with TestClient(node.create_app()) as client:
        data = client.get("/metrics").json()
    assert "requests" in data
    assert data["requests"]["total_requests"] == 1
    assert data["requests"]["total_tokens"] == 10


def test_prometheus_endpoint_exposition_format():
    node = _mock_node()
    with TestClient(node.create_app()) as client:
        resp = client.get("/metrics/prometheus")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "# TYPE daios_active_requests gauge" in body
    assert "daios_requests_total" in body
    assert 'node="metrics-node"' in body
