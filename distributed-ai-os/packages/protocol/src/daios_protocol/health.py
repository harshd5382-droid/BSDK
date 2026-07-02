"""Health and cluster status types exposed by the node API."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field
from daios_protocol.scheduling import SchedulerStats


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


class NodeCapabilities(BaseModel):
    """Hardware and inference-backend capabilities of a single node.

    ``gpu_available`` reports whether GPU *hardware* was detected on the
    machine; ``rpc_devices`` reports which devices the node's llama.cpp/RPC
    binary actually exposes (a CPU-only build exposes no GPU device even when
    hardware is present). Fields are None when a metric is unavailable.
    """

    node_id: str | None = None
    ram_total_gb: float | None = None
    ram_available_gb: float | None = None
    cpu_model: str | None = None
    cpu_cores: int | None = None
    gpu_available: bool = False
    gpu_backend: str | None = None  # e.g. "cuda" — hardware detection source
    gpu_name: str | None = None
    gpu_vram_total_gb: float | None = None
    gpu_vram_available_gb: float | None = None
    rpc_ready: bool | None = None  # ggml-rpc-server process running (workers)
    rpc_host: str | None = None
    rpc_port: int | None = None
    # Devices the local ggml-rpc-server binary exposes, parsed from its
    # startup banner (measured) — empty when unknown.
    rpc_devices: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DeviceAllocation(BaseModel):
    """Planned allocation for one llama.cpp device (local or RPC)."""

    name: str  # e.g. "CUDA0", "RPC[10.0.0.2:50052]"
    kind: str = "unknown"  # local_gpu | rpc | unknown
    endpoint: str | None = None  # host:port for RPC devices
    node_id: str | None = None
    memory_type: str = "unknown"  # vram | ram | unknown
    total_gb: float | None = None
    free_gb: float | None = None
    reserve_gb: float = 0.0
    usable_gb: float = 0.0
    weight: float = 0.0
    share_percent: float | None = None
    excluded_reason: str | None = None
    # "measured" when memory figures come from the llama.cpp device probe,
    # "estimated" when derived from advertised capabilities.
    source: str = "measured"


class DistributionDiagnostics(BaseModel):
    """Observability for distributed tensor placement (coordinator)."""

    policy: str | None = None  # None = legacy (no distribution block)
    backend: str = "llama.cpp"
    tensor_split: str | None = None
    devices: list[DeviceAllocation] = Field(default_factory=list)
    rpc_endpoints: list[str] = Field(default_factory=list)  # effective now
    launched_rpc_endpoints: list[str] | None = None  # llama-server started with
    excluded_endpoints: dict[str, str] = Field(default_factory=dict)
    topology_stale: bool = False
    restart_state: str = "idle"  # idle | pending | running | success | failed
    restart_error: str | None = None
    effective_command: list[str] | None = None  # secret-redacted
    fallback_reason: str | None = None
    active_requests: int = 0
    local_capabilities: NodeCapabilities | None = None
    workers: dict[str, NodeCapabilities] = Field(default_factory=dict)


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
    queue_depth: int = 0
    capabilities: NodeCapabilities | None = None
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
    capabilities: NodeCapabilities | None = None


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
    capabilities: NodeCapabilities | None = None


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
    scheduler: SchedulerStats | None = None
    # Worker hosts temporarily excluded from the RPC pool (still cluster members).
    paused_workers: list[str] = Field(default_factory=list)
    # Tensor-placement diagnostics (coordinators running the real backend).
    distribution: DistributionDiagnostics | None = None
