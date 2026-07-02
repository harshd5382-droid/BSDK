"""Ephemeral per-request coordinator for Generation 2."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from daios_protocol.config import NodeConfig
from daios_protocol.health import CoordinatorLease, MemberInfo, MemberStatus

from daios_node.resources import score_peer_for_placement, should_refuse_work

logger = logging.getLogger(__name__)

DEFAULT_LEASE_SECONDS = 300


class CoordinatorRegistry:
    """In-memory registry of ephemeral per-request coordinator leases."""

    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self._leases: dict[str, CoordinatorLease] = {}

    def create_lease(
        self,
        members: list[MemberInfo],
        request_id: str | None = None,
        worker_endpoints: list[str] | None = None,
    ) -> CoordinatorLease:
        rid = request_id or str(uuid.uuid4())
        workers = worker_endpoints if worker_endpoints is not None else self._select_workers(members)
        now = datetime.now(timezone.utc)
        lease = CoordinatorLease(
            request_id=rid,
            coordinator_node_id=self.config.node_id,
            coordinator_host=self.config.network.bind_host,
            worker_endpoints=workers,
            created_at=now,
            expires_at=now + timedelta(seconds=DEFAULT_LEASE_SECONDS),
        )
        self._leases[rid] = lease
        logger.info("Created coordinator lease %s with workers %s", rid, workers)
        return lease

    def _select_workers(self, members: list[MemberInfo]) -> list[str]:
        """Greedy placement: pick peers with best score."""
        candidates: list[tuple[float, MemberInfo]] = []
        for m in members:
            if m.status != MemberStatus.ALIVE:
                continue
            if m.node_id == self.config.node_id:
                continue
            if not m.advertisement:
                candidates.append((0.5, m))
                continue
            if should_refuse_work(m.advertisement, self.config.resource_caps):
                continue
            rtt = m.advertisement.rtt_ms.get(self.config.node_id, 0.0)
            score = score_peer_for_placement(m.advertisement, rtt)
            candidates.append((score, m))

        candidates.sort(key=lambda x: x[0], reverse=True)
        endpoints = [f"{m.host}:{m.rpc_port}" for _, m in candidates[:4]]
        if not endpoints and self.config.runs_rpc_server:
            endpoints.append(f"127.0.0.1:{self.config.network.rpc_port}")
        return endpoints

    def get_lease(self, request_id: str) -> CoordinatorLease | None:
        lease = self._leases.get(request_id)
        if lease is None:
            return None
        if lease.expires_at < datetime.now(timezone.utc):
            del self._leases[request_id]
            return None
        return lease

    def active_leases(self) -> list[CoordinatorLease]:
        now = datetime.now(timezone.utc)
        expired = [k for k, v in self._leases.items() if v.expires_at < now]
        for k in expired:
            del self._leases[k]
        return list(self._leases.values())

    def complete_lease(self, request_id: str) -> None:
        self._leases.pop(request_id, None)

    def merge_remote_leases(self, leases: list[CoordinatorLease]) -> None:
        for lease in leases:
            existing = self._leases.get(lease.request_id)
            if existing is None or lease.created_at > existing.created_at:
                if lease.expires_at >= datetime.now(timezone.utc):
                    self._leases[lease.request_id] = lease
