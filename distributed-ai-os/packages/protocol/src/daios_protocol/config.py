"""Node configuration schema for DAIOS nodes (Generation 1+)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


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
    extra_args: list[str] = Field(default_factory=list)

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
