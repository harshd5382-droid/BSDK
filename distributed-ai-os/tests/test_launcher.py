"""Launcher unit and integration tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daios_protocol.config import NodeRole, load_config
from daios_launcher.config_gen import StartRequest, build_node_config, write_runtime_config
from daios_launcher.system_info import gather_system_info, get_lan_ip, is_local_address
from daios_launcher.validation import validate_start_request

ROOT = Path(__file__).resolve().parents[1]


def test_get_lan_ip():
    ip = get_lan_ip()
    assert ip.count(".") == 3


def test_gather_system_info():
    info = gather_system_info(ROOT)
    assert info.cpu_count >= 1
    assert info.ram_total_gb > 0
    assert isinstance(info.models, list)


def test_build_coordinator_config():
    req = StartRequest(
        role=NodeRole.COORDINATOR,
        peer_host="192.168.1.42",
        model_path="models/test.gguf",
        backend="mock",
    )
    config = build_node_config(req, node_id="test-coord", project_root=ROOT)
    assert config.role == NodeRole.COORDINATOR
    assert len(config.peers) == 1
    assert config.peers[0].host == "192.168.1.42"
    assert config.inference.backend == "mock"
    assert config.inference.llama_server_bin.endswith("llama-server")


def test_build_worker_config():
    req = StartRequest(role=NodeRole.WORKER, backend="mock")
    config = build_node_config(req, node_id="test-worker")
    assert config.role == NodeRole.WORKER
    assert config.runs_rpc_server
    assert not config.runs_coordinator
    assert config.network.bind_host == "0.0.0.0"


def test_write_runtime_config_roundtrip(tmp_path):
    req = StartRequest(
        role=NodeRole.COORDINATOR,
        peer_host="10.0.0.2",
        backend="mock",
    )
    config = build_node_config(req)
    path = write_runtime_config(config, tmp_path)
    loaded = load_config(path)
    assert loaded.node_id == config.node_id
    assert loaded.role == config.role
    assert loaded.peers[0].host == "10.0.0.2"


@pytest.fixture
def launcher_client():
    from daios_launcher.app import LauncherApp

    app = LauncherApp(ROOT).create_app()
    with TestClient(app) as client:
        yield client


def test_launcher_system_endpoint(launcher_client):
    resp = launcher_client.get("/api/launcher/system")
    assert resp.status_code == 200
    data = resp.json()
    assert "lan_ip" in data
    assert "cpu_count" in data


def test_launcher_status_stopped(launcher_client):
    resp = launcher_client.get("/api/launcher/status")
    assert resp.status_code == 200
    assert resp.json()["node_state"] == "stopped"


@pytest.fixture
def mock_coordinator_running(launcher_client):
    launcher_client.post(
        "/api/launcher/stop",
    )
    resp = launcher_client.post(
        "/api/launcher/start",
        json={
            "role": "coordinator",
            "backend": "mock",
            "api_port": 8010,
            "peer_host": "192.168.254.99",
            "peer_rpc_port": 50053,
            "peer_api_port": 8011,
        },
    )
    assert resp.status_code == 200, resp.text
    time.sleep(2)
    yield launcher_client
    launcher_client.post("/api/launcher/stop")


def test_launcher_start_stop_mock(mock_coordinator_running):
    client = mock_coordinator_running
    status = client.get("/api/launcher/status").json()
    assert status["node_state"] == "running"
    assert status["role"] == "coordinator"

    stop = client.post("/api/launcher/stop")
    assert stop.status_code == 200
    assert client.get("/api/launcher/status").json()["node_state"] == "stopped"


def test_launcher_chat_mock(mock_coordinator_running):
    client = mock_coordinator_running
    resp = client.post(
        "/api/launcher/chat",
        json={"message": "hello", "stream": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "choices" in data
    assert "DAIOS mock" in data["choices"][0]["message"]["content"]


def test_build_coordinator_resolves_model_path():
    req = StartRequest(
        role=NodeRole.COORDINATOR,
        peer_host="192.168.1.42",
        model_path="qwen2.5-0.5b-instruct-q4_k_m.gguf",
        backend="llama.cpp",
    )
    config = build_node_config(req, project_root=ROOT)
    assert config.inference.model_path
    assert Path(config.inference.model_path).is_file()


def test_validate_rejects_coordinator_with_local_peer():
    lan = get_lan_ip()
    req = StartRequest(role=NodeRole.COORDINATOR, peer_host=lan, backend="mock")
    err = validate_start_request(req)
    assert err is not None
    assert "cannot be this PC" in err


def test_validate_rejects_worker_with_peer_host():
    req = StartRequest(role=NodeRole.WORKER, peer_host="192.168.1.42", backend="mock")
    err = validate_start_request(req)
    assert err is not None


def test_validate_accepts_worker():
    req = StartRequest(role=NodeRole.WORKER, backend="mock")
    assert validate_start_request(req) is None


def test_is_local_address():
    assert is_local_address("127.0.0.1")
    assert is_local_address(get_lan_ip())
    assert not is_local_address("192.168.254.99")


def test_launcher_rejects_coordinator_pointing_at_self(launcher_client):
    lan = get_lan_ip()
    resp = launcher_client.post(
        "/api/launcher/stop",
    )
    resp = launcher_client.post(
        "/api/launcher/start",
        json={
            "role": "coordinator",
            "backend": "mock",
            "peer_host": lan,
        },
    )
    assert resp.status_code == 400
    assert "cannot be this PC" in resp.json()["detail"]


def test_system_includes_local_ips(launcher_client):
    resp = launcher_client.get("/api/launcher/system")
    data = resp.json()
    assert "local_ips" in data
    assert get_lan_ip() in data["local_ips"]
