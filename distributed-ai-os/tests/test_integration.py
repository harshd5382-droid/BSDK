"""Integration tests for the node daemon (mock backend)."""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER_CONFIG = ROOT / "examples" / "two-node" / "worker-mock.yaml"
COORD_CONFIG = ROOT / "examples" / "two-node" / "coordinator-mock.yaml"


@pytest.fixture(scope="module")
def mock_cluster():
    """Start worker and coordinator nodes for integration tests."""
    worker = subprocess.Popen(
        [sys.executable, "-m", "daios_node.cli", "-c", str(WORKER_CONFIG)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)
    coord = subprocess.Popen(
        [sys.executable, "-m", "daios_node.cli", "-c", str(COORD_CONFIG)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)
    yield
    coord.terminate()
    worker.terminate()
    coord.wait(timeout=10)
    worker.wait(timeout=10)


@pytest.mark.asyncio
async def test_worker_health(mock_cluster):
    async with httpx.AsyncClient() as client:
        response = await client.get("http://127.0.0.1:8001/health")
    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "worker-mock"
    assert data["role"] == "worker"


@pytest.mark.asyncio
async def test_coordinator_health(mock_cluster):
    async with httpx.AsyncClient() as client:
        response = await client.get("http://127.0.0.1:8000/health")
    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "coordinator-mock"
    assert data["inference"]["backend"] == "mock"


@pytest.mark.asyncio
async def test_cluster_status(mock_cluster):
    async with httpx.AsyncClient() as client:
        response = await client.get("http://127.0.0.1:8000/api/v1/cluster")
    assert response.status_code == 200
    data = response.json()
    assert data["generation"] == 1
    assert len(data["peers"]) == 1


@pytest.mark.asyncio
async def test_openai_chat_completion(mock_cluster):
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "http://127.0.0.1:8000/v1/chat/completions",
            json={
                "model": "daios-mock-7b",
                "messages": [{"role": "user", "content": "ping"}],
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert "DAIOS mock" in data["choices"][0]["message"]["content"]


@pytest.mark.asyncio
async def test_peer_check_reachable():
    from daios_protocol.config import PeerConfig
    from daios_node.peers import check_peer

    server = await asyncio.start_server(
        lambda r, w: asyncio.create_task(_echo_close(r, w)),
        "127.0.0.1",
        0,
    )
    port = server.sockets[0].getsockname()[1]
    async with server:
        peer = PeerConfig(id="test", host="127.0.0.1", rpc_port=port)
        status = await check_peer(peer, timeout=2.0)
        assert status.reachable


async def _echo_close(reader, writer):
    writer.close()
    await writer.wait_closed()
