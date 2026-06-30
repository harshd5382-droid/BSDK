"""Tests for coordinator worker proxy."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from daios_launcher.worker_proxy import get_worker_status


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_get_worker_status_falls_back_to_node_health():
    http = AsyncMock()

    async def fake_get(url, **kwargs):
        if ":8090/" in url:
            raise httpx.ConnectError("refused", request=httpx.Request("GET", url))
        if ":8001/health" in url:
            return _Resp(
                200,
                {
                    "node_id": "worker-8001",
                    "role": "worker",
                    "uptime_seconds": 42.0,
                },
            )
        raise AssertionError(url)

    http.get = fake_get

    status = await get_worker_status(http, "192.168.1.164", "token", 8001)
    assert status["node_state"] == "running"
    assert status["remote_control"] == "node_only"
    assert status["role"] == "worker"


@pytest.mark.asyncio
async def test_get_worker_status_uses_launcher_when_available():
    http = AsyncMock()

    async def fake_get(url, **kwargs):
        if ":8090/" in url:
            return _Resp(
                200,
                {
                    "launcher": "ok",
                    "node_state": "running",
                    "role": "worker",
                },
            )
        raise AssertionError(url)

    http.get = fake_get

    status = await get_worker_status(http, "192.168.1.164", "token", 8001)
    assert status["remote_control"] == "launcher"
    assert status["launcher"] == "ok"
