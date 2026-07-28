"""mDNS-based peer discovery for Generation 2 clusters."""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from daios_protocol.config import NodeConfig
from daios_protocol.health import MemberInfo, MemberStatus

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_daios._tcp.local."

try:
    from zeroconf import NonUniqueNameException, ServiceInfo
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

    _ZEROCONF_AVAILABLE = True
except ImportError:
    _ZEROCONF_AVAILABLE = False
    AsyncZeroconf = None  # type: ignore[misc, assignment]
    AsyncServiceBrowser = None  # type: ignore[misc, assignment]
    AsyncServiceInfo = None  # type: ignore[misc, assignment]
    ServiceInfo = None  # type: ignore[misc, assignment]
    NonUniqueNameException = Exception  # type: ignore[misc, assignment]


# The LAN address is stamped into every gossip message and every membership
# view — including one per peer per heartbeat round and one per chat request —
# so the route lookup below runs far too often to do unconditionally. It only
# changes when the machine changes network, so a short TTL is plenty.
_LAN_IP_TTL = 30.0
_lan_ip_lock = threading.Lock()
_lan_ip_value: str | None = None
_lan_ip_ts: float = 0.0


def _get_lan_ip() -> str:
    global _lan_ip_value, _lan_ip_ts
    now = time.monotonic()
    with _lan_ip_lock:
        if _lan_ip_value is not None and now - _lan_ip_ts < _LAN_IP_TTL:
            return _lan_ip_value
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                ip = sock.getsockname()[0]
        except OSError:
            ip = "127.0.0.1"
        _lan_ip_value = ip
        _lan_ip_ts = now
        return ip


def _decode_txt_value(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _service_info_to_member(info: ServiceInfo | AsyncServiceInfo) -> MemberInfo | None:
    props = info.properties or {}
    node_id = _decode_txt_value(props.get(b"node_id", b""))
    if not node_id:
        return None
    role = _decode_txt_value(props.get(b"role", b"hybrid"))
    api_port = int(_decode_txt_value(props.get(b"api_port", b"8000")) or "8000")
    rpc_port = int(_decode_txt_value(props.get(b"rpc_port", b"50052")) or "50052")
    host = socket.inet_ntoa(info.addresses[0]) if info.addresses else "127.0.0.1"
    return MemberInfo(
        node_id=node_id,
        host=host,
        api_port=api_port,
        rpc_port=rpc_port,
        role=role,
        status=MemberStatus.ALIVE,
        last_seen=datetime.now(timezone.utc),
    )


if _ZEROCONF_AVAILABLE:

    class _AsyncDaiosListener:
        """Listener for AsyncServiceBrowser.

        The browser invokes the sync ``add_service``/``update_service``/
        ``remove_service`` callbacks from inside the event loop; we schedule
        the (async) service-record resolution as a task on the same loop.
        """

        def __init__(
            self,
            aiozc: AsyncZeroconf,
            on_discovered: Callable[[MemberInfo], None],
            self_node_id: str,
        ) -> None:
            self._aiozc = aiozc
            self._on_discovered = on_discovered
            self._self_node_id = self_node_id
            self._seen: set[str] = set()

        def _schedule_resolve(self, type_: str, name: str) -> None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop_policy().get_event_loop()
            loop.create_task(self._resolve(type_, name))

        def add_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
            self._schedule_resolve(type_, name)

        def update_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
            self._schedule_resolve(type_, name)

        def remove_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
            pass

        async def _resolve(self, type_: str, name: str) -> None:
            info = AsyncServiceInfo(type_, name)
            # async_request returns False when resolution times out; the info
            # object itself is always truthy, so check the return value.
            if not await info.async_request(self._aiozc.zeroconf, 3000):
                return
            member = _service_info_to_member(info)
            if not member or member.node_id == self._self_node_id:
                return
            self._seen.add(member.node_id)
            self._on_discovered(member)


class DiscoveryService:
    """Advertise and discover DAIOS nodes on the LAN via mDNS."""

    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self._discovered: dict[str, MemberInfo] = {}
        self._aiozc: AsyncZeroconf | None = None
        self._browser: AsyncServiceBrowser | None = None
        self._running = False

    @property
    def available(self) -> bool:
        return _ZEROCONF_AVAILABLE and self.config.discovery.mdns

    def get_discovered_peers(self) -> list[MemberInfo]:
        return [
            m for m in self._discovered.values() if m.node_id != self.config.node_id
        ]

    def _on_discovered(self, member: MemberInfo) -> None:
        if member.node_id == self.config.node_id:
            return
        self._discovered[member.node_id] = member
        logger.info(
            "Discovered peer %s at %s:%s", member.node_id, member.host, member.api_port
        )

    async def start(self) -> None:
        if not self.config.discovery_enabled:
            return
        if not self.available:
            logger.warning(
                "Discovery enabled but zeroconf not installed; falling back to manual peers"
            )
            return
        if self._running:
            return
        self._running = True
        host = _get_lan_ip()
        api_port = self.config.network.api_port
        rpc_port = self.config.network.rpc_port
        props = {
            b"node_id": self.config.node_id.encode(),
            b"role": self.config.role.value.encode(),
            b"api_port": str(api_port).encode(),
            b"rpc_port": str(rpc_port).encode(),
            b"cluster": self.config.discovery.cluster_name.encode(),
        }
        service_name = (
            f"{self.config.discovery.cluster_name}-{self.config.node_id}.{SERVICE_TYPE}"
        )
        # Derive a per-node ``server`` (host A-record) name. Without this,
        # zeroconf falls back to the machine hostname, so two nodes on the same
        # host (e.g. a local coordinator + worker, or multiple test nodes)
        # collide on the same A-record and the second registration raises
        # NonUniqueNameException -- killing discovery for that node.
        server_name = f"{self.config.discovery.cluster_name}-{self.config.node_id}.local."
        self._aiozc = AsyncZeroconf()
        info = ServiceInfo(
            SERVICE_TYPE,
            service_name,
            addresses=[socket.inet_aton(host)],
            port=api_port,
            properties=props,
            server=server_name,
        )

        # Always start the browser so we can discover peers even if our own
        # advertisement fails to register (a non-unique name must not stop us
        # from finding the rest of the cluster).
        listener = _AsyncDaiosListener(
            self._aiozc, self._on_discovered, self.config.node_id
        )
        self._browser = AsyncServiceBrowser(
            self._aiozc.zeroconf, SERVICE_TYPE, listener=listener
        )

        try:
            await self._aiozc.async_register_service(info)
            logger.info(
                "mDNS discovery started for cluster %s on %s (api %s, rpc %s)",
                self.config.discovery.cluster_name,
                host,
                api_port,
                rpc_port,
            )
        except NonUniqueNameException:
            logger.warning(
                "mDNS service name %s already registered (another node on this "
                "host?); continuing in discover-only mode",
                service_name,
            )

    async def stop(self) -> None:
        if not self._running:
            return
        try:
            if self._browser:
                await self._browser.async_cancel()
                self._browser = None
            if self._aiozc:
                await self._aiozc.async_unregister_all_services()
                await self._aiozc.async_close()
                self._aiozc = None
        except Exception:
            logger.exception("Error stopping mDNS discovery")
        self._running = False

    async def run_loop(self) -> None:
        """Background task that keeps discovery alive."""
        if not self.config.discovery_enabled:
            return
        try:
            await self.start()
        except Exception:
            logger.exception("Failed to start mDNS discovery")
            self._running = False
            return
        try:
            while self._running:
                await asyncio.sleep(self.config.discovery.advertise_interval)
        finally:
            await self.stop()
