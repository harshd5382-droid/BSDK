"""Tests for daios_protocol configuration."""

from pathlib import Path

import pytest

from daios_protocol.config import NodeConfig, NodeRole, load_config


EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "two-node"


def test_load_coordinator_config():
    config = load_config(EXAMPLES / "coordinator.yaml")
    assert config.node_id == "coordinator-1"
    assert config.role == NodeRole.COORDINATOR
    assert config.runs_coordinator
    assert not config.runs_rpc_server
    assert len(config.peers) == 1
    assert config.peers[0].host == "worker"


def test_load_worker_config():
    config = load_config(EXAMPLES / "worker.yaml")
    assert config.role == NodeRole.WORKER
    assert config.runs_rpc_server
    assert not config.runs_coordinator


def test_rpc_endpoints_coordinator():
    config = load_config(EXAMPLES / "coordinator.yaml")
    endpoints = config.rpc_endpoints()
    assert endpoints == ["worker:50052"]


def test_rpc_endpoints_hybrid():
    raw = {
        "node_id": "hybrid-1",
        "role": "hybrid",
        "network": {"rpc_port": 50052},
        "peers": [{"id": "w1", "host": "10.0.0.2", "rpc_port": 50052}],
    }
    config = NodeConfig.model_validate(raw)
    endpoints = config.rpc_endpoints()
    assert "127.0.0.1:50052" in endpoints
    assert "10.0.0.2:50052" in endpoints


def test_invalid_backend():
    with pytest.raises(ValueError, match="backend"):
        NodeConfig.model_validate(
            {"node_id": "x", "role": "worker", "inference": {"backend": "invalid"}}
        )
