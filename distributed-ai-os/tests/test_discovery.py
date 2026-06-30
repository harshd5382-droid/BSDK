"""Tests for Generation 2 discovery."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from daios_protocol.config import NodeConfig
from daios_node.discovery import DiscoveryService, _get_lan_ip


def _config(**kwargs) -> NodeConfig:
    base = {
        "node_id": "node-a",
        "role": "coordinator",
        "discovery": {"enabled": True, "cluster_name": "test-cluster"},
    }
    base.update(kwargs)
    return NodeConfig.model_validate(base)


def test_discovery_disabled_no_start():
    config = NodeConfig.model_validate({"node_id": "x", "role": "worker"})
    svc = DiscoveryService(config)
    svc.start()
    assert svc.get_discovered_peers() == []


def test_get_lan_ip_returns_string():
    ip = _get_lan_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0


def test_discovery_on_discovered_callback():
    config = _config()
    svc = DiscoveryService(config)
    member = MagicMock()
    member.node_id = "peer-b"
    svc._on_discovered(member)
    assert "peer-b" in svc._discovered


def test_discovery_ignores_self():
    config = _config(node_id="node-a")
    svc = DiscoveryService(config)
    member = MagicMock()
    member.node_id = "node-a"
    svc._on_discovered(member)
    assert svc.get_discovered_peers() == []


@pytest.mark.asyncio
async def test_discovery_run_loop_disabled():
    config = NodeConfig.model_validate({"node_id": "x", "role": "worker"})
    svc = DiscoveryService(config)
    await svc.run_loop()  # should return immediately
