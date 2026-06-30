"""Tests for launcher settings, models, and security."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from daios_launcher.models_manager import list_models
from daios_launcher.security import LauncherTokenMiddleware
from daios_launcher.settings import LauncherSettings
from daios_launcher.update import get_version

ROOT = Path(__file__).resolve().parents[1]


def test_settings_ensure_token(tmp_path, monkeypatch):
    path = tmp_path / "launcher.json"
    monkeypatch.setattr("daios_launcher.settings.SETTINGS_PATH", path)
    settings = LauncherSettings.load()
    token = settings.ensure_token()
    assert len(token) > 20
    reloaded = LauncherSettings.load()
    assert reloaded.cluster_token == token


def test_list_models_empty(tmp_path):
    assert list_models(tmp_path / "models") == []


def test_list_models_with_files(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "a.gguf").write_bytes(b"x" * 1024)
    result = list_models(models, active="a.gguf")
    assert len(result) == 1
    assert result[0]["active"] is True


def test_get_version_git_repo():
    info = get_version(ROOT)
    assert info.commit or info.error


def test_token_middleware_blocks_remote_without_token():
    app = FastAPI()
    app.add_middleware(LauncherTokenMiddleware, token="secret-token")

    @app.get("/api/launcher/status")
    async def status():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/launcher/status")
    assert resp.status_code == 401

    resp = client.get(
        "/api/launcher/status",
        headers={"X-DAIOS-Token": "secret-token"},
    )
    assert resp.status_code == 200
