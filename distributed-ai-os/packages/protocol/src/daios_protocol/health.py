"""Health and cluster status types exposed by the node API."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ProcessState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


class ResourceUsage(BaseModel):
    """Live CPU / RAM usage for a single node."""

    cpu_percent: float | None = None
    cpu_count: int | None = None
    ram_used_gb: float | None = None
    ram_total_gb: float | None = None
    ram_percent: float | None = None


class ModelUsage(BaseModel):
    """AI model load / activity for a single node."""

    status: str = "offline"  # offline | idle | active
    usage_percent: float | None = None
    detail: str | None = None
    model_name: str | None = None


class PeerStatus(BaseModel):
    id: str
    host: str
    rpc_port: int
    reachable: bool
    latency_ms: float | None = None
    error: str | None = None
    resources: ResourceUsage | None = None
    model_usage: ModelUsage | None = None


class InferenceStatus(BaseModel):
    backend: str
    llama_server: ProcessState = ProcessState.STOPPED
    rpc_server: ProcessState = ProcessState.STOPPED
    model_path: str | None = None
    openai_base_url: str | None = None


class NodeHealth(BaseModel):
    node_id: str
    role: str
    status: str = "ok"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    inference: InferenceStatus
    uptime_seconds: float = 0.0
    resources: ResourceUsage | None = None
    model_usage: ModelUsage | None = None


class ClusterStatus(BaseModel):
    """Generation 1 cluster view (manual peer list)."""

    coordinator_node_id: str
    peers: list[PeerStatus]
    rpc_endpoints: list[str]
    inbound_rpc_clients: int = 0
    generation: int = 1
    local_resources: ResourceUsage | None = None
    local_model_usage: ModelUsage | None = None
    coordinator_ip: str | None = None
