"""Peer health checks for Generation 1 manual cluster configuration."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from daios_protocol.config import NodeConfig, PeerConfig
from daios_protocol.health import ModelUsage, PeerStatus, ResourceUsage

logger = logging.getLogger(__name__)


def _tcp_probe(host: str, port: int, timeout: float) -> tuple[bool, str | None]:
    """Blocking TCP connect run in a thread pool."""
    import socket

    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        return True, None
    except OSError as exc:
        return False, str(exc)
    finally:
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()


async def check_peer(peer: PeerConfig, timeout: float = 3.0) -> PeerStatus:
    """Probe a peer's liveness.

    When the peer exposes a node API port, that HTTP ``/health`` endpoint is the
    authoritative reachability signal. The GGML RPC server (``ggml-rpc-server``)
    is single-threaded and serves only one connection at a time with a tiny
    accept backlog, so probing its raw TCP port while it is busy serving an
    active inference session yields false "unreachable" results -- and the probe
    sockets themselves pile up in the accept queue and wedge the server. The node
    API (uvicorn) handles concurrent requests and stays responsive regardless of
    RPC activity, so we prefer it and avoid touching the RPC port entirely.

    Only when no API port is configured do we fall back to a raw TCP probe of the
    RPC port.
    """
    host = peer.host
    start = time.perf_counter()

    if peer.api_port:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"http://{host}:{peer.api_port}/health")
            latency_ms = (time.perf_counter() - start) * 1000.0
            if response.status_code >= 400:
                return PeerStatus(
                    id=peer.id,
                    host=peer.host,
                    rpc_port=peer.rpc_port,
                    reachable=False,
                    error=f"health endpoint returned {response.status_code}",
                )
            resources: ResourceUsage | None = None
            model_usage: ModelUsage | None = None
            try:
                payload = response.json()
                raw = payload.get("resources")
                if raw:
                    resources = ResourceUsage.model_validate(raw)
                raw_model = payload.get("model_usage")
                if raw_model:
                    model_usage = ModelUsage.model_validate(raw_model)
            except (ValueError, TypeError):
                resources = None
                model_usage = None
            return PeerStatus(
                id=peer.id,
                host=peer.host,
                rpc_port=peer.rpc_port,
                reachable=True,
                latency_ms=latency_ms,
                resources=resources,
                model_usage=model_usage,
            )
        except httpx.HTTPError as exc:
            return PeerStatus(
                id=peer.id,
                host=peer.host,
                rpc_port=peer.rpc_port,
                reachable=False,
                error=f"health check failed: {exc}",
            )

    reachable, error = await asyncio.to_thread(_tcp_probe, host, peer.rpc_port, timeout)
    latency_ms = (time.perf_counter() - start) * 1000.0 if reachable else None

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


_LOOPBACK_HEX = {"0100007F", "00000000000000000000000001000000"}


def count_inbound_rpc_clients(port: int) -> int:
    """Count established inbound TCP connections to the local RPC port.

    A worker is passive: it never tracks the coordinator as a peer, so its
    dashboard cannot derive "connected" from a peer probe. However, the
    coordinator's llama-server holds a persistent connection to the worker's
    RPC port for the duration of an inference session, so a non-zero count of
    established connections to that port means a coordinator is attached.

    Reads ``/proc/net/tcp`` and ``/proc/net/tcp6`` (Linux). Loopback peers are
    ignored. Returns 0 on unsupported platforms or on any read error.
    """
    total = 0
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as fh:
                lines = fh.readlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue
            local, remote, state = parts[1], parts[2], parts[3]
            if state != "01":  # TCP_ESTABLISHED
                continue
            try:
                local_port = int(local.rsplit(":", 1)[1], 16)
            except (ValueError, IndexError):
                continue
            if local_port != port:
                continue
            remote_ip = remote.rsplit(":", 1)[0]
            if remote_ip in _LOOPBACK_HEX:
                continue
            total += 1
    return total
