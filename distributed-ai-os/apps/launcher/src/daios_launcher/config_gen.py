"""Generate runtime node YAML from launcher UI input."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from daios_launcher.gguf_context import infer_context_size

import yaml
from pydantic import BaseModel

from daios_protocol.config import (
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
DEFAULT_CHAT_MAX_TOKENS = 512


class StartRequest(BaseModel):
    role: NodeRole
    peer_host: str | None = None
    peer_rpc_port: int = 50052
    peer_api_port: int = 8001
    model_path: str | None = None
    backend: str = "llama.cpp"
    api_port: int = 8000
    rpc_port: int = 50052
    discovery_enabled: bool = False
    cluster_name: str = "daios"


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
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _default_threads() -> int:
    """Use most cores for inference, leaving one for the OS and API."""
    return max(1, (os.cpu_count() or 2) - 1)


def _resolve_context_size(model_path: str | None, backend: str) -> int:
    """Cap context for fast CPU/RPC inference (native 128k is far too large)."""
    if backend != "llama.cpp" or not model_path:
        return 0
    native = infer_context_size(model_path)
    if native is None:
        return INFERENCE_CONTEXT_CAP
    return min(native, INFERENCE_CONTEXT_CAP)


def _resolve_gpu_layers(backend: str) -> int:
    if backend != "llama.cpp":
        return 0
    return 99 if _has_nvidia_gpu() else 0


def build_node_config(
    req: StartRequest,
    node_id: str | None = None,
    project_root: Path | None = None,
) -> NodeConfig:
    root = project_root or Path.cwd()
    peers: list[PeerConfig] = []
    if not req.discovery_enabled and req.role in (NodeRole.COORDINATOR, NodeRole.HYBRID) and req.peer_host:
        peers.append(
            PeerConfig(
                id="peer-1",
                host=req.peer_host,
                rpc_port=req.peer_rpc_port,
                api_port=req.peer_api_port,
            )
        )

    discovery = DiscoveryConfig(
        enabled=req.discovery_enabled,
        cluster_name=req.cluster_name,
    )

    resolved_model = _resolve_model_path(req.model_path, root)

    inference = InferenceConfig(
        backend=req.backend,
        llama_server_bin=_runtime_binary(root, "llama-server"),
        rpc_server_bin=_runtime_binary(root, "ggml-rpc-server"),
        model_path=resolved_model,
        llama_server_port=8080,
        n_gpu_layers=_resolve_gpu_layers(req.backend),
        context_size=_resolve_context_size(resolved_model, req.backend),
        threads=_default_threads(),
        rpc_cache=True,
    )

    # When discovery is enabled, bind to all interfaces so other PCs on the LAN
    # can reach this node's API port for gossip heartbeats. Without this, a
    # coordinator bound to 127.0.0.1 would be undiscoverable from remote hosts.
    if req.discovery_enabled:
        bind_host = "0.0.0.0"
    else:
        bind_host = "0.0.0.0" if req.role == NodeRole.WORKER else "127.0.0.1"

    return NodeConfig(
        node_id=node_id or f"{req.role.value}-{req.api_port}",
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
