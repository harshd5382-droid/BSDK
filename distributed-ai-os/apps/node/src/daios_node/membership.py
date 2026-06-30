"""Gossip-based cluster membership for Generation 2."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from daios_protocol.config import NodeConfig
from daios_protocol.health import MemberInfo, MemberStatus, MembershipView
from daios_protocol.messages import HeartbeatMessage, HeartbeatResponse, LeaveMessage

from daios_node.coordinator import CoordinatorRegistry
from daios_node.discovery import DiscoveryService, _get_lan_ip
from daios_node.resources import gather_advertisement, gather_resources

logger = logging.getLogger(__name__)


def _advertise_host(config: NodeConfig) -> str:
    """Host this node should advertise to peers.

    When bound to ``0.0.0.0`` (all interfaces, the Gen 2 default for discovery)
    or loopback, advertise the LAN IP so peers can actually reach us.
    """
    bind = config.network.bind_host
    if not bind or bind in ("0.0.0.0", "::", "127.0.0.1", "localhost"):
        return _get_lan_ip()
    return bind


class MembershipService:
    """Eventually-consistent membership with heartbeat gossip."""

    def __init__(
        self,
        config: NodeConfig,
        discovery: DiscoveryService,
        coordinator_registry: CoordinatorRegistry,
    ) -> None:
        self.config = config
        self.discovery = discovery
        self.coordinator_registry = coordinator_registry
        self._members: dict[str, MemberInfo] = {}
        self._membership_version = 0
        self._running = False
        self._http: httpx.AsyncClient | None = None
        self._rtt_ms: dict[str, float] = {}

    def _local_member(self) -> MemberInfo:
        ad = gather_advertisement(
            self.config,
            current_workload=len(self.coordinator_registry.active_leases()),
            rtt_ms=self._rtt_ms,
        )
        return MemberInfo(
            node_id=self.config.node_id,
            host=_advertise_host(self.config),
            api_port=self.config.network.api_port,
            rpc_port=self.config.network.rpc_port,
            role=self.config.role.value,
            status=MemberStatus.ALIVE,
            last_seen=datetime.now(timezone.utc),
            resources=gather_resources(),
            advertisement=ad,
            membership_version=self._membership_version,
        )

    def _upsert_member(self, member: MemberInfo) -> None:
        if member.node_id == self.config.node_id:
            return
        existing = self._members.get(member.node_id)
        # Preserve a routable host: if the incoming member advertises a
        # non-routable placeholder (0.0.0.0 / loopback) but we already know a
        # real address (e.g. from mDNS), keep the real one.
        if existing and member.host in ("0.0.0.0", "::", "127.0.0.1", "localhost", ""):
            member = member.model_copy(update={"host": existing.host})
        if existing is None or member.membership_version >= existing.membership_version:
            self._members[member.node_id] = member

    def _merge_members(self, members: list[MemberInfo]) -> None:
        for m in members:
            self._upsert_member(m)

    def _mark_suspect_dead(self) -> None:
        now = datetime.now(timezone.utc)
        timeout = timedelta(seconds=self.config.membership.failure_timeout)
        for node_id, member in list(self._members.items()):
            if now - member.last_seen > timeout:
                member.status = MemberStatus.DEAD
            elif now - member.last_seen > timeout / 2:
                member.status = MemberStatus.SUSPECT

    def get_membership_view(self) -> MembershipView:
        self._mark_suspect_dead()
        local = self._local_member()
        all_members = [local] + [
            m for m in self._members.values() if m.status != MemberStatus.DEAD
        ]
        return MembershipView(
            local_node_id=self.config.node_id,
            members=all_members,
            generation=2,
            membership_version=self._membership_version,
            active_leases=self.coordinator_registry.active_leases(),
            cluster_name=self.config.discovery.cluster_name,
        )

    def get_alive_worker_hosts(self) -> list[str]:
        hosts: list[str] = []
        for m in self._members.values():
            if m.status == MemberStatus.ALIVE and m.role in ("worker", "hybrid"):
                hosts.append(m.host)
        return hosts

    async def handle_heartbeat(self, msg: HeartbeatMessage) -> HeartbeatResponse:
        self._upsert_member(msg.sender)
        if msg.advertisement:
            member = self._members.get(msg.sender.node_id)
            if member:
                member.advertisement = msg.advertisement
        self.coordinator_registry.merge_remote_leases(msg.active_leases)
        if msg.membership_version > self._membership_version:
            self._membership_version = msg.membership_version
        return HeartbeatResponse(
            sender=self._local_member(),
            membership_version=self._membership_version,
            members=list(self._members.values()),
        )

    async def handle_leave(self, msg: LeaveMessage) -> None:
        member = self._members.get(msg.node_id)
        if member:
            member.status = MemberStatus.LEAVING
            del self._members[msg.node_id]
        if msg.membership_version > self._membership_version:
            self._membership_version = msg.membership_version

    async def _send_heartbeat(self, member: MemberInfo) -> None:
        if not self._http:
            return
        start = time.perf_counter()
        msg = HeartbeatMessage(
            sender=self._local_member(),
            membership_version=self._membership_version,
            advertisement=gather_advertisement(
                self.config,
                current_workload=len(self.coordinator_registry.active_leases()),
                rtt_ms=self._rtt_ms,
            ),
            active_leases=self.coordinator_registry.active_leases(),
        )
        url = f"http://{member.host}:{member.api_port}/api/v1/internal/heartbeat"
        try:
            response = await self._http.post(url, json=msg.model_dump(mode="json"), timeout=5.0)
            elapsed = (time.perf_counter() - start) * 1000
            self._rtt_ms[member.node_id] = elapsed
            if response.status_code == 200:
                resp = HeartbeatResponse.model_validate(response.json())
                self._merge_members(resp.members)
                self._upsert_member(resp.sender)
                if resp.membership_version > self._membership_version:
                    self._membership_version = resp.membership_version
                member.last_seen = datetime.now(timezone.utc)
                member.status = MemberStatus.ALIVE
        except httpx.HTTPError as exc:
            logger.debug("Heartbeat to %s failed: %s", member.node_id, exc)

    async def _heartbeat_loop(self) -> None:
        while self._running:
            discovered = self.discovery.get_discovered_peers()
            for peer in discovered:
                self._upsert_member(peer)
            for member in list(self._members.values()):
                if member.status != MemberStatus.DEAD:
                    await self._send_heartbeat(member)
            self._mark_suspect_dead()
            await asyncio.sleep(self.config.membership.heartbeat_interval)

    async def announce_leave(self) -> None:
        if not self._http:
            return
        msg = LeaveMessage(
            node_id=self.config.node_id,
            membership_version=self._membership_version,
        )
        for member in list(self._members.values()):
            url = f"http://{member.host}:{member.api_port}/api/v1/internal/leave"
            try:
                await self._http.post(url, json=msg.model_dump(mode="json"), timeout=3.0)
            except httpx.HTTPError:
                pass

    async def run(self) -> None:
        if not self.config.discovery_enabled:
            return
        self._running = True
        self._http = httpx.AsyncClient(timeout=10.0)
        try:
            await self._heartbeat_loop()
        finally:
            await self.announce_leave()
            if self._http:
                await self._http.aclose()
                self._http = None
            self._running = False

    def stop(self) -> None:
        self._running = False
