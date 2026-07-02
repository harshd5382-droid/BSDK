"""Bounded retry for coordinator-side inference forwarding.

llama.cpp RPC cannot reroute a single request mid-flight, but when a worker drops
the membership service marks it dead and llama-server restarts with the remaining
nodes. During that window the coordinator's forward can hit a transient
``ConnectError`` / 5xx. This helper retries those transient failures (with a
peer-resync hook) so a worker dropping doesn't surface as a hard error to clients.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


async def forward_with_retry(
    send: Callable[[], Awaitable],
    *,
    retries: int,
    is_transient: Callable[[object], bool],
    on_retry: Callable[[int], Awaitable] | None = None,
    sleep: Callable[[float], Awaitable] = asyncio.sleep,
    backoff: float = 0.5,
):
    """Call ``send()``; retry while the result or raised error is transient.

    ``is_transient`` is called with either the awaited result or the raised
    exception. ``on_retry(attempt)`` runs before each retry (e.g. resync peers).
    Non-transient exceptions propagate immediately.
    """
    attempt = 0
    while True:
        try:
            result = await send()
        except Exception as exc:  # noqa: BLE001 - re-raised below if not transient
            if is_transient(exc) and attempt < retries:
                attempt += 1
                if on_retry is not None:
                    await on_retry(attempt)
                await sleep(backoff)
                continue
            raise
        if is_transient(result) and attempt < retries:
            attempt += 1
            if on_retry is not None:
                await on_retry(attempt)
            await sleep(backoff)
            continue
        return result
