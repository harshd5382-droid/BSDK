"""Generate runtime node YAML from launcher UI input."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from pathlib import Path

from daios_launcher.gguf_context import infer_context_size

import yaml
from pydantic import BaseModel, Field

from daios_protocol.config import (
    DistributionConfig,
    DiscoveryConfig,
    InferenceConfig,
    NetworkConfig,
    NodeConfig,
    NodeRole,
    PeerConfig,
)


# Context window. 131072 = full native 128k context for Qwen-class models.
# Note: a larger context grows the KV cache and can slow per-token speed on CPU/RPC.
INFERENCE_CONTEXT_CAP = 131072
# Coordinators pooling worker RPC must use a modest context — 128k KV cache on a
# 14B model across CPU/RPC can take many minutes to allocate or OOM, which looks
# like "loading model" forever in chat. Matches coordinator-distributed.yaml.
DISTRIBUTED_CONTEXT_CAP = 4096
DEFAULT_CHAT_MAX_TOKENS = 512


class StartRequest(BaseModel):
    role: NodeRole
    peer_host: str | None = None
    # Multiple manually-entered worker IPs (Gen 1 static peers). When present,
    # these are used instead of ``peer_host`` so the dashboard can connect more
    # than one worker PC. Each becomes a static PeerConfig entry.
    peer_hosts: list[str] = Field(default_factory=list)
    peer_rpc_port: int = 50052
    peer_api_port: int = 8001
    model_path: str | None = None
    backend: str = "llama.cpp"
    api_port: int = 8000
    rpc_port: int = 50052
    discovery_enabled: bool = False
    cluster_name: str = "daios"
    # Workload balancing across devices (coordinator only). `worker_share` is the
    # percentage (0-100) of the model to push onto remote worker(s); the rest stays
    # on this PC. `tensor_split` (raw llama.cpp value, e.g. "20,80") overrides it.
    worker_share: int | None = None
    tensor_split: str | None = None

    def effective_peer_hosts(self) -> list[str]:
        """Resolved, de-duplicated, non-empty list of worker IPs to peer with."""
        raw = self.peer_hosts if self.peer_hosts else ([self.peer_host] if self.peer_host else [])
        seen: set[str] = set()
        out: list[str] = []
        for host in raw:
            if not host:
                continue
            h = host.strip()
            if h and h not in seen:
                seen.add(h)
                out.append(h)
        return out


def compute_tensor_split(worker_share: int, num_workers: int = 1) -> str:
    """Build a llama.cpp ``--tensor-split`` value from a worker-share percentage.

    Device order is local-first: ``"<local>,<worker...>"``. With one worker,
    ``worker_share=80`` -> ``"20,80"`` (most of the model runs on the worker PC).
    Multiple workers split the worker share evenly.
    """
    worker_share = max(0, min(100, worker_share))
    local = 100 - worker_share
    if num_workers <= 1:
        return f"{local},{worker_share}"
    per = worker_share / num_workers
    return ",".join([str(local)] + [f"{per:g}"] * num_workers)


def _resolve_model_path(model_path: str | None, project_root: Path) -> str | None:
    if not model_path:
        return None
    path = Path(model_path)
    if not path.is_absolute():
        path = project_root / path
    if not path.is_file():
        alt = project_root / "models" / Path(model_path).name
        if alt.is_file():
            path = alt
    return str(path)


def _runtime_binary(project_root: Path, name: str) -> str:
    """Resolve a worker binary (llama-server / ggml-rpc-server).

    Frozen production builds materialize native binaries under
    ``%LOCALAPPDATA%\\BSDK\\bin``; dev builds resolve them from the project venv.
    """
    from daios_launcher import paths

    if paths.is_frozen():
        exe = name + (".exe" if sys.platform == "win32" else "")
        return str(paths.bin_dir() / exe)

    from daios_launcher.platform_utils import resolve_venv_binary

    return resolve_venv_binary(project_root, name)


def _has_nvidia_gpu() -> bool:
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=2,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _default_threads() -> int:
    """Use most cores for inference, leaving one for the OS and API."""
    return max(1, (os.cpu_count() or 2) - 1)


def _resolve_context_size(
    model_path: str | None, backend: str, *, distributed: bool = False
) -> int:
    """Cap context for inference. Distributed CPU/RPC runs use a small cap."""
    if backend != "llama.cpp" or not model_path:
        return 0
    native = infer_context_size(model_path)
    cap = DISTRIBUTED_CONTEXT_CAP if distributed else INFERENCE_CONTEXT_CAP
    if native is None:
        return cap
    return min(native, cap)


def _default_node_id(role: NodeRole, api_port: int) -> str:
    """Per-machine node id safe for YAML, gossip, and mDNS registration.

    ``{role}-{api_port}`` alone collides when every worker uses the default
    api_port 8001 — both PCs try to register ``daios-worker-8001`` on mDNS and
    only one advertisement survives (the other runs discover-only).
    """
    try:
        hostname = socket.gethostname().lower()
    except OSError:
        hostname = ""
    slug = re.sub(r"[^a-z0-9]+", "-", hostname).strip("-")
    if not slug:
        slug = "host"
    slug = slug[:40]
    return f"{role.value}-{slug}-{api_port}"


def _resolve_gpu_layers(backend: str) -> int:
    if backend != "llama.cpp":
        return 0
    return 99 if _has_nvidia_gpu() else 0


def _coordinator_distribution(role: NodeRole) -> DistributionConfig | None:
    """Workload-balancing policy that keeps the coordinator workable.

    Only coordinators/hybrids place tensors, so only they need a distribution
    policy. Workers get ``None`` (unchanged legacy behavior).
    """
    if role not in (NodeRole.COORDINATOR, NodeRole.HYBRID):
        return None
    return DistributionConfig(
        policy="worker_preferred",
        # Keep a healthy headroom on the master so the OS / dashboard / editor
        # stay responsive while workers carry the model.
        coordinator_reserve_ram_gb=6.0,
        coordinator_reserve_vram_gb=1.0,
        worker_reserve_ram_gb=2.0,
        worker_reserve_vram_gb=0.5,
        # Demote coordinator-local devices so workers carry the bulk of the
        # model; 0.2 = a local device needs ~5x the usable memory of a worker
        # to attract the same share.
        coordinator_weight_scale=0.2,
        wait_for_workers_seconds=30.0,
        restart_debounce_seconds=10.0,
    )


def build_node_config(
    req: StartRequest,
    node_id: str | None = None,
    project_root: Path | None = None,
) -> NodeConfig:
    root = project_root or Path.cwd()
    peer_hosts = req.effective_peer_hosts()
    peers: list[PeerConfig] = []
    if not req.discovery_enabled and req.role in (NodeRole.COORDINATOR, NodeRole.HYBRID):
        for idx, host in enumerate(peer_hosts):
            peers.append(
                PeerConfig(
                    id=f"peer-{idx + 1}",
                    host=host,
                    rpc_port=req.peer_rpc_port,
                    api_port=req.peer_api_port,
                )
            )

    discovery = DiscoveryConfig(
        enabled=req.discovery_enabled,
        cluster_name=req.cluster_name,
    )

    resolved_model = _resolve_model_path(req.model_path, root)

    distributed = req.role in (NodeRole.COORDINATOR, NodeRole.HYBRID) and (
        req.discovery_enabled or bool(peer_hosts)
    )

    # Resolve workload balancing: explicit tensor_split wins; otherwise derive it
    # from worker_share for the known peer count (coordinator only).
    tensor_split = req.tensor_split
    if tensor_split is None and req.worker_share is not None and req.role in (
        NodeRole.COORDINATOR,
        NodeRole.HYBRID,
    ):
        tensor_split = compute_tensor_split(req.worker_share, max(1, len(peers)))

    inference = InferenceConfig(
        backend=req.backend,
        llama_server_bin=_runtime_binary(root, "llama-server"),
        rpc_server_bin=_runtime_binary(root, "ggml-rpc-server"),
        model_path=resolved_model,
        llama_server_port=8080,
        n_gpu_layers=_resolve_gpu_layers(req.backend),
        context_size=_resolve_context_size(resolved_model, req.backend, distributed=distributed),
        threads=_default_threads(),
        rpc_cache=True,
        tensor_split=tensor_split,
        # Coordinators push model tensors onto worker RPC devices and keep a
        # RAM reserve on this PC, so a 14B-class model does not exhaust the
        # master's memory and the master stays usable for the dashboard/OS.
        # `worker_preferred` demotes coordinator-local devices via
        # coordinator_weight_scale; with discovery it also defers llama-server
        # start until workers are pooled, so the model never loads onto the
        # master alone. Explicit tensor_split still wins (see inference.py).
        distribution=_coordinator_distribution(req.role),
    )

    # When discovery is enabled, bind to all interfaces so other PCs on the LAN
    # can reach this node's API port for gossip heartbeats. Without this, a
    # coordinator bound to 127.0.0.1 would be undiscoverable from remote hosts.
    if req.discovery_enabled:
        bind_host = "0.0.0.0"
    else:
        bind_host = "0.0.0.0" if req.role == NodeRole.WORKER else "127.0.0.1"

    return NodeConfig(
        node_id=node_id or _default_node_id(req.role, req.api_port),
        role=req.role,
        network=NetworkConfig(
            bind_host=bind_host,
            api_port=req.api_port,
            rpc_port=req.rpc_port,
        ),
        peers=peers,
        inference=inference,
        discovery=discovery,
    )


def write_runtime_config(config: NodeConfig, runtime_dir: Path) -> Path:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    path = runtime_dir / f"{config.node_id}.yaml"
    data = config.model_dump(mode="json")
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
    return path
