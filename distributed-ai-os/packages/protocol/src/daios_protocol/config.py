"""Node configuration schema for DAIOS nodes (Generation 1+)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class NodeRole(str, Enum):
    """Node role defaults. In Generation 2+ any node may coordinate per-request."""

    COORDINATOR = "coordinator"
    WORKER = "worker"
    HYBRID = "hybrid"


class PeerConfig(BaseModel):
    """Manually configured peer (Generation 1 — no auto-discovery yet)."""

    id: str
    host: str
    rpc_port: int = 50052
    api_port: int | None = None


class NetworkConfig(BaseModel):
    bind_host: str = "0.0.0.0"
    api_port: int = 8000
    rpc_port: int = 50052


class DiscoveryConfig(BaseModel):
    """Automatic peer discovery (Generation 2+)."""

    enabled: bool = False
    mdns: bool = True
    cluster_name: str = "daios"
    advertise_interval: float = 5.0
    listen_port: int | None = None  # defaults to network.api_port


class SecurityConfig(BaseModel):
    """Transport and API security (Generation 2+)."""

    mtls_enabled: bool = False
    ca_cert: str | None = None
    node_cert: str | None = None
    node_key: str | None = None
    api_token: str | None = None
    auto_generate_certs: bool = True


class MembershipConfig(BaseModel):
    """Gossip membership and heartbeat settings (Generation 2+)."""

    heartbeat_interval: float = 5.0
    failure_timeout: float = 15.0
    gossip_interval: float = 10.0


class ResourceCapsConfig(BaseModel):
    """Administrator-configured contribution limits."""

    max_cpu_percent: float | None = None
    max_ram_gb: float | None = None
    max_gpu_percent: float | None = None


class ManualAllocation(BaseModel):
    """Explicit per-node allocation weight for ``policy: manual``."""

    weight: float = Field(ge=0.0)


class DistributionConfig(BaseModel):
    """Resource-distribution policy for real llama.cpp inference.

    Opt-in: when the ``inference.distribution`` block is absent from the YAML
    the node behaves exactly as before (llama.cpp's own default split, no
    generated ``--tensor-split``). All memory figures are in GB.
    """

    policy: str = "auto"
    coordinator_reserve_ram_gb: float = Field(default=4.0, ge=0.0)
    coordinator_reserve_vram_gb: float = Field(default=1.0, ge=0.0)
    worker_reserve_ram_gb: float = Field(default=2.0, ge=0.0)
    worker_reserve_vram_gb: float = Field(default=0.5, ge=0.0)
    minimum_worker_vram_gb: float = Field(default=0.0, ge=0.0)
    prefer_worker_devices: bool = True
    # Weight multiplier applied to CPU-backed (system-RAM) devices under
    # ``auto`` — memory alone must not attract compute to a slow device.
    cpu_device_discount: float = Field(default=0.5, gt=0.0, le=1.0)
    # RTT (ms) at which an RPC device's auto weight is halved.
    latency_discount_ms: float = Field(default=200.0, gt=0.0)
    # Weight multiplier for coordinator-local devices under worker_preferred.
    coordinator_weight_scale: float = Field(default=0.2, ge=0.0, le=1.0)
    # How long the coordinator waits for worker RPC ports before launching
    # llama-server (also the grace period for discovery to find workers).
    wait_for_workers_seconds: float = Field(default=30.0, ge=0.0)
    # Topology changes must be stable this long before llama-server restarts.
    restart_debounce_seconds: float = Field(default=10.0, ge=0.0)
    manual_allocations: dict[str, ManualAllocation] = Field(default_factory=dict)

    @field_validator("policy")
    @classmethod
    def validate_policy(cls, value: str) -> str:
        allowed = {"auto", "balanced", "worker_preferred", "manual"}
        if value not in allowed:
            raise ValueError(f"distribution.policy must be one of {sorted(allowed)}")
        return value

    @field_validator("manual_allocations", mode="before")
    @classmethod
    def coerce_manual_allocations(cls, value: Any) -> Any:
        """Accept both ``node: 0.7`` and ``node: {weight: 0.7}`` shapes."""
        if isinstance(value, dict):
            return {
                key: ({"weight": val} if isinstance(val, (int, float)) else val)
                for key, val in value.items()
            }
        return value

    @model_validator(mode="after")
    def validate_manual_policy(self) -> "DistributionConfig":
        if self.policy == "manual" and not self.manual_allocations:
            raise ValueError("policy 'manual' requires manual_allocations")
        return self


class InferenceConfig(BaseModel):
    """llama.cpp / GGML RPC inference backend settings."""

    backend: str = "llama.cpp"
    llama_server_bin: str = "llama-server"
    rpc_server_bin: str = "ggml-rpc-server"
    model_path: str | None = None
    llama_server_port: int = 8080
    n_gpu_layers: int = 99
    tensor_split: str | None = None
    context_size: int = 0  # 0 = use model native context (llama.cpp default)
    threads: int | None = None
    rpc_cache: bool = False
    auto_restart: bool = True
    max_restarts: int = 5
    extra_args: list[str] = Field(default_factory=list)
    # None = legacy behavior (backward compatible with pre-distribution YAML).
    distribution: DistributionConfig | None = None

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, value: str) -> str:
        allowed = {"llama.cpp", "mock"}
        if value not in allowed:
            raise ValueError(f"backend must be one of {allowed}")
        return value


class NodeConfig(BaseModel):
    """Root configuration for a single DAIOS node."""

    node_id: str
    role: NodeRole
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    peers: list[PeerConfig] = Field(default_factory=list)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    membership: MembershipConfig = Field(default_factory=MembershipConfig)
    resource_caps: ResourceCapsConfig = Field(default_factory=ResourceCapsConfig)
    scheduler: "SchedulerConfig" = Field(default_factory=lambda: SchedulerConfig())

    @property
    def runs_rpc_server(self) -> bool:
        return self.role in (NodeRole.WORKER, NodeRole.HYBRID)

    @property
    def runs_coordinator(self) -> bool:
        return self.role in (NodeRole.COORDINATOR, NodeRole.HYBRID)

    @property
    def discovery_enabled(self) -> bool:
        return self.discovery.enabled

    def rpc_endpoints(self, peer_hosts: list[str] | None = None) -> list[str]:
        """Return host:port strings for --rpc flag (local + peers).

        When ``peer_hosts`` is provided (Generation 2 discovery), those hosts
        replace the static ``peers[]`` list.
        """
        endpoints: list[str] = []
        if self.runs_rpc_server:
            endpoints.append(f"127.0.0.1:{self.network.rpc_port}")
        if peer_hosts is not None:
            for host in peer_hosts:
                endpoints.append(f"{host}:{self.network.rpc_port}")
        else:
            for peer in self.peers:
                endpoints.append(f"{peer.host}:{peer.rpc_port}")
        return endpoints


def load_config(path: str | Path) -> NodeConfig:
    """Load node configuration from a YAML file."""
    config_path = Path(path)
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    return NodeConfig.model_validate(raw)


class SchedulerConfig(BaseModel):
    """Generation 3 scheduling configuration (feature-flagged)."""

    enabled: bool = False
    steal_interval: float = 2.0
    max_queue_depth: int = 100
    interactive_weight: float = 4.0
    background_weight: float = 1.0
    default_tenant_weight: float = 1.0
    max_concurrent: int = 1
    tenant_weights: dict[str, float] = Field(default_factory=dict)
