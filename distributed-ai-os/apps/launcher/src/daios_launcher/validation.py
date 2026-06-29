"""Start-request validation and peer reachability helpers."""

from __future__ import annotations

import asyncio
import time

from daios_launcher.config_gen import StartRequest
from daios_launcher.system_info import get_lan_ip, is_local_address
from daios_node.peers import check_peer
from daios_protocol.config import NodeRole, PeerConfig
from daios_protocol.health import PeerStatus


def validate_start_request(req: StartRequest, local_ips: set[str] | None = None) -> str | None:
    """Return an error message if the start request is invalid, else None."""
    from daios_launcher.system_info import get_local_addresses

    local_ips = local_ips or get_local_addresses()

    if req.role == NodeRole.WORKER:
        if req.peer_host:
            return "Worker role must not point at another PC. Use Coordinator on the other machine."
        return None

    if req.role in (NodeRole.COORDINATOR, NodeRole.HYBRID):
        if not req.peer_host or not req.peer_host.strip():
            return "Enter the worker PC's LAN IP (not this computer's address)."
        peer = req.peer_host.strip()
        if is_local_address(peer, local_ips):
            lan = get_lan_ip()
            return (
                f"Worker IP cannot be this PC ({peer}). "
                f"This machine is {lan} — choose Worker here and Coordinator on the other PC."
            )

    return None


async def wait_for_peer(
    peer: PeerConfig,
    *,
    timeout: float = 20.0,
    interval: float = 1.5,
    probe_timeout: float = 3.0,
) -> PeerStatus:
    """Retry peer probe until reachable or timeout (coordinator preflight)."""
    deadline = time.monotonic() + timeout
    last: PeerStatus | None = None
    while time.monotonic() < deadline:
        last = await check_peer(peer, timeout=probe_timeout)
        if last.reachable and not last.error:
            return last
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(interval, remaining))
    assert last is not None
    return last
