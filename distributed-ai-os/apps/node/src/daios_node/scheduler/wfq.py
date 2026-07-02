"""Weighted fair queue with strict priority bands."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from daios_protocol.config import SchedulerConfig
from daios_protocol.scheduling import Priority


@dataclass(slots=True)
class QueueItem:
    request_id: str
    tenant_id: str
    estimated_tokens: int
    priority: Priority
    payload: Any = None


class FairQueue:
    """Strict priority with per-tenant weighted fair selection inside a band."""

    def __init__(self, config: SchedulerConfig) -> None:
        self._config = config
        self._bands: dict[Priority, dict[str, deque[QueueItem]]] = {
            Priority.INTERACTIVE: defaultdict(deque),
            Priority.BACKGROUND: defaultdict(deque),
            Priority.BATCH: defaultdict(deque),
        }
        self._vt: dict[str, float] = defaultdict(float)

    def push(self, item: QueueItem) -> None:
        self._bands[item.priority][item.tenant_id].append(item)

    def pop_next(self) -> QueueItem | None:
        for band in (Priority.INTERACTIVE, Priority.BACKGROUND, Priority.BATCH):
            tenant = self._pick_tenant(self._bands[band])
            if tenant is None:
                continue
            q = self._bands[band][tenant]
            item = q.popleft()
            if not q:
                del self._bands[band][tenant]
            self._vt[tenant] += max(item.estimated_tokens, 1) / self._weight(tenant, band)
            return item
        return None

    def steal_candidate(self) -> QueueItem | None:
        for band in (Priority.BACKGROUND, Priority.BATCH):
            tenant = self._pick_tenant(self._bands[band])
            if tenant is None:
                continue
            q = self._bands[band][tenant]
            item = q.popleft()
            if not q:
                del self._bands[band][tenant]
            return item
        return None

    def depth(self) -> int:
        total = 0
        for band_queues in self._bands.values():
            total += sum(len(q) for q in band_queues.values())
        return total

    def tenant_depths(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for band_queues in self._bands.values():
            for tenant, q in band_queues.items():
                counts[tenant] += len(q)
        return dict(counts)

    def virtual_time(self) -> dict[str, float]:
        return dict(self._vt)

    def _pick_tenant(self, queues: dict[str, deque[QueueItem]]) -> str | None:
        if not queues:
            return None
        return min(queues.keys(), key=lambda t: self._vt[t])

    def _weight(self, tenant_id: str, band: Priority) -> float:
        tenant_weight = self._config.tenant_weights.get(tenant_id, self._config.default_tenant_weight)
        if band == Priority.INTERACTIVE:
            return max(tenant_weight * self._config.interactive_weight, 0.01)
        return max(tenant_weight * self._config.background_weight, 0.01)
