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


def test_gen2_discovery_config_defaults():
    config = NodeConfig.model_validate({"node_id": "x", "role": "worker"})
    assert config.discovery.enabled is False
    assert config.discovery.cluster_name == "daios"
    assert config.discovery_enabled is False


def test_gen2_discovery_config_enabled():
    config = NodeConfig.model_validate(
        {
            "node_id": "x",
            "role": "hybrid",
            "discovery": {"enabled": True, "cluster_name": "home"},
        }
    )
    assert config.discovery_enabled is True
    assert config.discovery.cluster_name == "home"


def test_rpc_endpoints_with_peer_hosts():
    config = NodeConfig.model_validate(
        {
            "node_id": "c1",
            "role": "coordinator",
            "peers": [{"id": "w1", "host": "manual", "rpc_port": 50052}],
        }
    )
    assert config.rpc_endpoints(["10.0.0.2"]) == ["10.0.0.2:50052"]
    assert config.rpc_endpoints() == ["manual:50052"]


def test_load_discovered_coordinator_config():
    discovered = Path(__file__).resolve().parents[1] / "examples" / "two-node-discovered"
    config = load_config(discovered / "coordinator-mdns.yaml")
    assert config.discovery.enabled is True
    assert config.discovery.cluster_name == "daios-home"


def test_load_all_example_yamls_backwards_compatible():
    root = Path(__file__).resolve().parents[1] / "examples"
    for yaml_path in root.rglob("*.yaml"):
        loaded = load_config(yaml_path)
        assert loaded.node_id
        assert loaded.role in NodeRole


def test_scheduler_and_inference_restart_defaults():
    config = NodeConfig.model_validate({"node_id": "defaults", "role": "worker"})
    assert config.inference.auto_restart is True
    assert config.inference.max_restarts == 5
    assert config.scheduler.enabled is False
    assert config.scheduler.max_concurrent == 1


def test_rpc_endpoints_honours_explicit_peer_ports():
    """Discovered workers advertise their own rpc_port; assuming ours pools nothing."""
    config = NodeConfig.model_validate({"node_id": "c", "role": "coordinator"})
    endpoints = config.rpc_endpoints(["10.0.0.2:60000", "10.0.0.3"])
    assert endpoints == ["10.0.0.2:60000", "10.0.0.3:50052"]
