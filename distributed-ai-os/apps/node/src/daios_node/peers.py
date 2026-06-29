"""Peer health checks for Generation 1 manual cluster configuration."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from daios_protocol.config import NodeConfig, PeerConfig
from daios_protocol.health import PeerStatus

logger = logging.getLogger(__name__)


async def check_peer(peer: PeerConfig, timeout: float = 3.0) -> PeerStatus:
    """Probe a peer's RPC port (TCP) and optional API health endpoint."""
    host, port = peer.host, peer.rpc_port
    start = time.perf_counter()
    reachable = False
    error: str | None = None

    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        reachable = True
    except (OSError, asyncio.TimeoutError) as exc:
        error = str(exc)

    latency_ms: float | None = None
    if reachable:
        latency_ms = (time.perf_counter() - start) * 1000.0

    if reachable and peer.api_port:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"http://{host}:{peer.api_port}/health")
                if response.status_code >= 500:
                    error = f"health endpoint returned {response.status_code}"
        except httpx.HTTPError as exc:
            error = f"health check failed: {exc}"

    return PeerStatus(
        id=peer.id,
        host=peer.host,
        rpc_port=peer.rpc_port,
        reachable=reachable,
        latency_ms=latency_ms,
        error=error,
    )


async def check_all_peers(config: NodeConfig) -> list[PeerStatus]:
    if not config.peers:
        return []
    return await asyncio.gather(*(check_peer(peer) for peer in config.peers))
