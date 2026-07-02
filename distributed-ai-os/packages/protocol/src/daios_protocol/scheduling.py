"""Protocol types for Generation 3 scheduling."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Priority(str, Enum):
    INTERACTIVE = "interactive"
    BACKGROUND = "background"
    BATCH = "batch"


class ScheduleRequest(BaseModel):
    request_id: str
    priority: Priority = Priority.INTERACTIVE
    model_id: str | None = None
    estimated_tokens: int = 0
    tenant_id: str | None = None
    latency_slo_ms: int | None = None


class NodePlacement(BaseModel):
    node_id: str
    rpc_endpoint: str
    layer_range: tuple[int, int] | None = None


class PlacementDecision(BaseModel):
    request_id: str
    workers: list[NodePlacement] = Field(default_factory=list)
    scheduler_version: int = 3
    score: float = 0.0
    slo_met: bool | None = None


class SchedulerStats(BaseModel):
    queue_depth: int = 0
    per_tenant_queued: dict[str, int] = Field(default_factory=dict)
    virtual_time: dict[str, float] = Field(default_factory=dict)
    dispatched: int = 0
    rejected: int = 0
    stolen: int = 0
    slo_warning: int = 0
