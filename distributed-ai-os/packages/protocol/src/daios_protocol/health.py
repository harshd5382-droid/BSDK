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


class PeerStatus(BaseModel):
    id: str
    host: str
    rpc_port: int
    reachable: bool
    latency_ms: float | None = None
    error: str | None = None


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


class ClusterStatus(BaseModel):
    """Generation 1 cluster view (manual peer list)."""

    coordinator_node_id: str
    peers: list[PeerStatus]
    rpc_endpoints: list[str]
    generation: int = 1
