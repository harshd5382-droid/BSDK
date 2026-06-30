"""Node configuration schema for Generation 1 manual two-node setup."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class NodeRole(str, Enum):
    """Generation 1 node roles. Every node runs the same software; role selects behavior."""

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

    @property
    def runs_rpc_server(self) -> bool:
        return self.role in (NodeRole.WORKER, NodeRole.HYBRID)

    @property
    def runs_coordinator(self) -> bool:
        return self.role in (NodeRole.COORDINATOR, NodeRole.HYBRID)

    def rpc_endpoints(self) -> list[str]:
        """Return host:port strings for --rpc flag (local + configured peers)."""
        endpoints: list[str] = []
        if self.runs_rpc_server:
            endpoints.append(f"127.0.0.1:{self.network.rpc_port}")
        for peer in self.peers:
            endpoints.append(f"{peer.host}:{peer.rpc_port}")
        return endpoints


def load_config(path: str | Path) -> NodeConfig:
    """Load node configuration from a YAML file."""
    config_path = Path(path)
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    return NodeConfig.model_validate(raw)
