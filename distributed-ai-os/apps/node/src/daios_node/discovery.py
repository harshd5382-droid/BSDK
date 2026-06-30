"""mDNS-based peer discovery for Generation 2 clusters."""

from __future__ import annotations

import asyncio
import logging
import socket
from datetime import datetime, timezone
from typing import Callable

from daios_protocol.config import NodeConfig
from daios_protocol.health import MemberInfo, MemberStatus

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_daios._tcp.local."

try:
    from zeroconf import ServiceInfo, ServiceListener, Zeroconf

    _ZEROCONF_AVAILABLE = True
except ImportError:
    _ZEROCONF_AVAILABLE = False
    Zeroconf = None  # type: ignore[misc, assignment]
    ServiceInfo = None  # type: ignore[misc, assignment]
    ServiceListener = object  # type: ignore[misc, assignment]


def _get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _decode_txt_value(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


if _ZEROCONF_AVAILABLE:

    class _DaiosServiceListener(ServiceListener):
        def __init__(self, on_discovered: Callable[[MemberInfo], None]) -> None:
            self._on_discovered = on_discovered
            self._seen: set[str] = set()

        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            if info is None:
                return
            member = _service_info_to_member(info)
            if member and member.node_id not in self._seen:
                self._seen.add(member.node_id)
                self._on_discovered(member)

        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            pass

        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            self.add_service(zc, type_, name)


def _service_info_to_member(info: ServiceInfo) -> MemberInfo | None:
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


class DiscoveryService:
    """Advertise and discover DAIOS nodes on the LAN via mDNS."""

    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self._discovered: dict[str, MemberInfo] = {}
        self._zc: Zeroconf | None = None
        self._listener: _DaiosServiceListener | None = None
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
        logger.info("Discovered peer %s at %s:%s", member.node_id, member.host, member.api_port)

    def start(self) -> None:
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
        service_name = f"{self.config.discovery.cluster_name}-{self.config.node_id}.{SERVICE_TYPE}"
        self._zc = Zeroconf()
        info = ServiceInfo(
            SERVICE_TYPE,
            service_name,
            addresses=[socket.inet_aton(host)],
            port=api_port,
            properties=props,
        )
        self._zc.register_service(info)
        self._listener = _DaiosServiceListener(self._on_discovered)
        self._zc.add_service_listener(SERVICE_TYPE, self._listener)
        logger.info("mDNS discovery started for cluster %s on %s", self.config.discovery.cluster_name, host)

    def stop(self) -> None:
        if not self._running or self._zc is None:
            return
        try:
            if self._listener:
                self._zc.remove_service_listener(self._listener)
            self._zc.unregister_all_services()
            self._zc.close()
        except Exception:
            logger.exception("Error stopping mDNS discovery")
        self._zc = None
        self._listener = None
        self._running = False

    async def run_loop(self) -> None:
        """Background task that keeps discovery alive."""
        if not self.config.discovery_enabled:
            return
        self.start()
        try:
            while self._running:
                await asyncio.sleep(self.config.discovery.advertise_interval)
        finally:
            self.stop()
