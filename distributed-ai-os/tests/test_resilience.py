"""Tests for bounded inference forward retry (worker-drop resilience)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from daios_node.app import NodeApp
from daios_node.resilience import forward_with_retry


async def _nosleep(_seconds: float) -> None:
    return None


def _transient(result: object) -> bool:
    return NodeApp._is_transient_failure(result)


def test_is_transient_failure_predicate():
    assert NodeApp._is_transient_failure(httpx.ConnectError("boom")) is True
    assert NodeApp._is_transient_failure(ValueError("nope")) is False
    assert NodeApp._is_transient_failure(SimpleNamespace(status_code=503)) is True
    assert NodeApp._is_transient_failure(SimpleNamespace(status_code=500)) is True
    assert NodeApp._is_transient_failure(SimpleNamespace(status_code=200)) is False


@pytest.mark.asyncio
async def test_succeeds_first_try():
    calls = {"n": 0}

    async def send():
        calls["n"] += 1
        return SimpleNamespace(status_code=200)

    result = await forward_with_retry(send, retries=2, is_transient=_transient, sleep=_nosleep)
    assert result.status_code == 200
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retries_transient_exception_then_succeeds():
    seq = [httpx.ConnectError("down"), SimpleNamespace(status_code=200)]
    retries_seen: list[int] = []

    async def send():
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def on_retry(attempt: int) -> None:
        retries_seen.append(attempt)

    result = await forward_with_retry(
        send, retries=2, is_transient=_transient, on_retry=on_retry, sleep=_nosleep
    )
    assert result.status_code == 200
    assert retries_seen == [1]  # recovered after one retry


@pytest.mark.asyncio
async def test_retries_5xx_response():
    seq = [SimpleNamespace(status_code=503), SimpleNamespace(status_code=200)]

    async def send():
        return seq.pop(0)

    result = await forward_with_retry(send, retries=2, is_transient=_transient, sleep=_nosleep)
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_gives_up_after_retries():
    async def send():
        raise httpx.ConnectError("permanently down")

    with pytest.raises(httpx.ConnectError):
        await forward_with_retry(send, retries=1, is_transient=_transient, sleep=_nosleep)


@pytest.mark.asyncio
async def test_non_transient_propagates_immediately():
    calls = {"n": 0}

    async def send():
        calls["n"] += 1
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        await forward_with_retry(send, retries=3, is_transient=_transient, sleep=_nosleep)
    assert calls["n"] == 1  # not retried
