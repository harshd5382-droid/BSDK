"""Integration tests for Generation 2 membership endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daios_protocol.config import NodeConfig
from daios_node.app import NodeApp


@pytest.fixture
def gen2_config(tmp_path):
    return NodeConfig.model_validate(
        {
            "node_id": "test-node",
            "role": "coordinator",
            "network": {"api_port": 18080, "rpc_port": 58052},
            "discovery": {"enabled": True, "mdns": False, "cluster_name": "test"},
            "inference": {"backend": "mock"},
            "membership": {"heartbeat_interval": 60, "failure_timeout": 120},
        }
    )


@pytest.fixture
def gen2_app(gen2_config):
    return NodeApp(gen2_config).create_app()


@pytest.mark.asyncio
async def test_membership_endpoint(gen2_app):
    transport = ASGITransport(app=gen2_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with gen2_app.router.lifespan_context(gen2_app):
            resp = await client.get("/api/v1/membership")
            assert resp.status_code == 200
            data = resp.json()
            assert data["local_node_id"] == "test-node"
            assert data["generation"] == 2


@pytest.mark.asyncio
async def test_cluster_gen2_shape(gen2_app):
    transport = ASGITransport(app=gen2_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with gen2_app.router.lifespan_context(gen2_app):
            resp = await client.get("/api/v1/cluster")
            assert resp.status_code == 200
            data = resp.json()
            assert data["generation"] == 2
            assert "membership" in data


@pytest.mark.asyncio
async def test_gen1_config_no_membership_endpoint():
    config = NodeConfig.model_validate(
        {
            "node_id": "g1",
            "role": "coordinator",
            "network": {"api_port": 18081},
            "inference": {"backend": "mock"},
        }
    )
    app = NodeApp(config).create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            resp = await client.get("/api/v1/membership")
            assert resp.status_code == 404
