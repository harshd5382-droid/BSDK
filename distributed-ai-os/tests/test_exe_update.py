"""Tests for coordinator-pushed exe updates (serve, verify, self-update dispatch)."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daios_launcher import exe_update
from daios_launcher.artifacts import ChecksumError, DownloadError


@pytest.fixture(autouse=True)
def _isolated_install_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DAIOS_HOME", str(tmp_path / "install"))
    exe_update._info_cache.clear()


def _make_exe(root: Path, content: bytes = b"exe-v1") -> Path:
    dist = root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    exe = dist / "daios-worker.exe"
    exe.write_bytes(content)
    return exe


# ----------------------------- serve side ------------------------------------


def test_serveable_worker_exe_none_without_build(tmp_path):
    assert exe_update.serveable_worker_exe(tmp_path) is None


def test_serveable_worker_exe_finds_dist_build(tmp_path):
    exe = _make_exe(tmp_path)
    assert exe_update.serveable_worker_exe(tmp_path) == exe


def test_exe_info_hash_and_cache(tmp_path):
    exe = _make_exe(tmp_path, b"hello world")
    info = exe_update.exe_info(exe)
    assert info["sha256"] == hashlib.sha256(b"hello world").hexdigest()
    assert info["size_bytes"] == len(b"hello world")
    # Second call with unchanged file returns the cached dict.
    assert exe_update.exe_info(exe) is info


def test_current_exe_sha256_none_when_not_frozen():
    assert exe_update.current_exe_sha256() is None


# ---------------------------- download side ----------------------------------


def _fake_downloader(content: bytes):
    def downloader(url: str, dest: Path) -> None:
        dest.write_bytes(content)

    return downloader


def test_download_worker_exe_verifies_and_stages():
    content = b"new exe bytes"
    sha = hashlib.sha256(content).hexdigest()
    staged = exe_update.download_worker_exe(
        "192.168.1.10", 8090, sha, "tok", downloader=_fake_downloader(content)
    )
    assert staged.read_bytes() == content
    assert staged.name == exe_update.STAGED_EXE_NAME


def test_download_worker_exe_rejects_checksum_mismatch():
    with pytest.raises(ChecksumError):
        exe_update.download_worker_exe(
            "192.168.1.10", 8090, "0" * 64, None, downloader=_fake_downloader(b"tampered")
        )


def test_download_worker_exe_rejects_empty():
    with pytest.raises(DownloadError):
        exe_update.download_worker_exe(
            "192.168.1.10", 8090, "0" * 64, None, downloader=_fake_downloader(b"")
        )


# ------------------------------ API side -------------------------------------


@pytest.fixture
def coordinator_client(tmp_path):
    from daios_launcher.app import LauncherApp

    app = LauncherApp(tmp_path / "project").create_app()
    with TestClient(app) as client:
        yield client, tmp_path / "project"


def test_worker_exe_info_404_without_build(coordinator_client):
    client, _root = coordinator_client
    resp = client.get("/api/launcher/worker-exe/info")
    assert resp.status_code == 404
    assert "build-exe.ps1" in resp.json()["detail"]


def test_worker_exe_info_and_download(coordinator_client):
    client, root = coordinator_client
    content = b"built exe"
    _make_exe(root, content)

    info = client.get("/api/launcher/worker-exe/info").json()
    assert info["sha256"] == hashlib.sha256(content).hexdigest()
    assert info["size_bytes"] == len(content)

    resp = client.get("/api/launcher/worker-exe")
    assert resp.status_code == 200
    assert resp.content == content


def test_update_frozen_requires_exe_sha(coordinator_client, monkeypatch):
    client, _root = coordinator_client
    from daios_launcher import app as app_mod

    monkeypatch.setattr(app_mod.paths, "is_frozen", lambda: True)
    resp = client.post("/api/launcher/update", json={})
    assert resp.status_code == 400
    assert "build-exe.ps1" in resp.json()["detail"]


def test_update_frozen_up_to_date_short_circuits(coordinator_client, monkeypatch):
    client, _root = coordinator_client
    from daios_launcher import app as app_mod

    monkeypatch.setattr(app_mod.paths, "is_frozen", lambda: True)
    monkeypatch.setattr(exe_update, "current_exe_sha256", lambda: "abc123")
    resp = client.post("/api/launcher/update", json={"exe_sha256": "ABC123"})
    assert resp.status_code == 200
    assert resp.json()["up_to_date"] is True


def test_update_frozen_downloads_and_schedules_installer(coordinator_client, monkeypatch):
    client, _root = coordinator_client
    from daios_launcher import app as app_mod

    monkeypatch.setattr(app_mod.paths, "is_frozen", lambda: True)
    monkeypatch.setattr(exe_update, "current_exe_sha256", lambda: "old")

    downloads: list[tuple] = []
    spawned: list[Path] = []

    def fake_download(host, port, sha, token, **kw):
        downloads.append((host, port, sha, token))
        return Path("staged.exe")

    monkeypatch.setattr(exe_update, "download_worker_exe", fake_download)
    monkeypatch.setattr(exe_update, "spawn_staged_installer", lambda p: spawned.append(p))

    resp = client.post(
        "/api/launcher/update",
        json={"exe_sha256": "newsha", "exe_source_host": "10.0.0.5", "exe_source_port": 9999},
    )
    assert resp.status_code == 200
    assert resp.json()["restarting"] is True
    assert downloads == [("10.0.0.5", 9999, "newsha", None)]

    deadline = time.monotonic() + 3.0
    while not spawned and time.monotonic() < deadline:
        time.sleep(0.05)
    assert spawned == [Path("staged.exe")]


def test_update_frozen_download_failure_is_502(coordinator_client, monkeypatch):
    client, _root = coordinator_client
    from daios_launcher import app as app_mod

    monkeypatch.setattr(app_mod.paths, "is_frozen", lambda: True)
    monkeypatch.setattr(exe_update, "current_exe_sha256", lambda: "old")

    def failing_download(*a, **k):
        raise DownloadError("boom")

    monkeypatch.setattr(exe_update, "download_worker_exe", failing_download)
    resp = client.post("/api/launcher/update", json={"exe_sha256": "newsha"})
    assert resp.status_code == 502
    assert "boom" in resp.json()["detail"]
