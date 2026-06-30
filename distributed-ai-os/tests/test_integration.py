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


def _free_ports(*ports: int) -> None:
    for port in ports:
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            capture_output=True,
            check=False,
        )


def _wait_for_health(url: str, expected_node_id: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                data = response.json()
                if data.get("node_id") == expected_node_id:
                    return
                last_error = f"wrong node_id: {data.get('node_id')}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Node at {url} not ready ({last_error})")


@pytest.fixture(scope="module")
def mock_cluster():
    """Start worker and coordinator nodes for integration tests."""
    _free_ports(8000, 8001, 50052, 50053)
    time.sleep(1)

    worker = subprocess.Popen(
        [sys.executable, "-m", "daios_node.cli", "-c", str(WORKER_CONFIG)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_health("http://127.0.0.1:8001/health", "worker-mock")
    except RuntimeError:
        worker.terminate()
        worker.wait(timeout=5)
        raise

    coord = subprocess.Popen(
        [sys.executable, "-m", "daios_node.cli", "-c", str(COORD_CONFIG)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_health("http://127.0.0.1:8000/health", "coordinator-mock")
    except RuntimeError:
        coord.terminate()
        worker.terminate()
        coord.wait(timeout=5)
        worker.wait(timeout=5)
        raise

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
