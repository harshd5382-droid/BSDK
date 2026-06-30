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


class MemberStatus(str, Enum):
    ALIVE = "alive"
    SUSPECT = "suspect"
    DEAD = "dead"
    LEAVING = "leaving"


class ResourceUsage(BaseModel):
    """Live CPU / RAM usage for a single node."""

    cpu_percent: float | None = None
    cpu_count: int | None = None
    ram_used_gb: float | None = None
    ram_total_gb: float | None = None
    ram_percent: float | None = None


class GpuInfo(BaseModel):
    name: str | None = None
    vram_total_gb: float | None = None
    vram_used_gb: float | None = None
    utilization_percent: float | None = None


class ResourceAdvertisement(BaseModel):
    """Full resource advertisement for Generation 2+ gossip."""

    node_id: str
    cpu_percent: float | None = None
    cpu_available_cores: int | None = None
    ram_total_gb: float | None = None
    ram_available_gb: float | None = None
    gpu: GpuInfo | None = None
    disk_free_gb: float | None = None
    bandwidth_mbps: float | None = None
    rtt_ms: dict[str, float] = Field(default_factory=dict)
    thermal_state: str | None = None
    battery_percent: float | None = None
    user_idle_seconds: float | None = None
    configured_caps: dict[str, float] = Field(default_factory=dict)
    current_workload: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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


class MemberInfo(BaseModel):
    """A cluster member discovered via gossip (Generation 2+)."""

    node_id: str
    host: str
    api_port: int
    rpc_port: int
    role: str
    status: MemberStatus = MemberStatus.ALIVE
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resources: ResourceUsage | None = None
    advertisement: ResourceAdvertisement | None = None
    model_usage: ModelUsage | None = None
    membership_version: int = 0


class CoordinatorLease(BaseModel):
    """Ephemeral per-request coordinator lease (Generation 2+)."""

    request_id: str
    coordinator_node_id: str
    coordinator_host: str
    worker_endpoints: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime


class MembershipView(BaseModel):
    """Generation 2 cluster membership view."""

    local_node_id: str
    members: list[MemberInfo]
    generation: int = 2
    membership_version: int = 0
    active_leases: list[CoordinatorLease] = Field(default_factory=list)
    cluster_name: str | None = None


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
    """Cluster view (Generation 1 manual peers or Generation 2 membership)."""

    coordinator_node_id: str | None = None
    peers: list[PeerStatus]
    rpc_endpoints: list[str]
    inbound_rpc_clients: int = 0
    generation: int = 1
    local_resources: ResourceUsage | None = None
    local_model_usage: ModelUsage | None = None
    coordinator_ip: str | None = None
    membership: MembershipView | None = None
