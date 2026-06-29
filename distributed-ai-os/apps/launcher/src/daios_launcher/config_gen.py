"""Generate runtime node YAML from launcher UI input."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from daios_protocol.config import InferenceConfig, NetworkConfig, NodeConfig, NodeRole, PeerConfig


class StartRequest(BaseModel):
    role: NodeRole
    peer_host: str | None = None
    peer_rpc_port: int = 50052
    peer_api_port: int = 8001
    model_path: str | None = None
    backend: str = "llama.cpp"
    api_port: int = 8000
    rpc_port: int = 50052


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


def _venv_binary(project_root: Path, name: str) -> str:
    candidate = project_root / ".venv" / "bin" / name
    return str(candidate) if candidate.is_file() else name


def build_node_config(
    req: StartRequest,
    node_id: str | None = None,
    project_root: Path | None = None,
) -> NodeConfig:
    root = project_root or Path.cwd()
    peers: list[PeerConfig] = []
    if req.role in (NodeRole.COORDINATOR, NodeRole.HYBRID) and req.peer_host:
        peers.append(
            PeerConfig(
                id="peer-1",
                host=req.peer_host,
                rpc_port=req.peer_rpc_port,
                api_port=req.peer_api_port,
            )
        )

    inference = InferenceConfig(
        backend=req.backend,
        llama_server_bin=_venv_binary(root, "llama-server"),
        rpc_server_bin=_venv_binary(root, "ggml-rpc-server"),
        model_path=_resolve_model_path(req.model_path, root),
        llama_server_port=8080,
        n_gpu_layers=99,
        context_size=2048,
        threads=2,
        rpc_cache=True,
    )

    return NodeConfig(
        node_id=node_id or f"{req.role.value}-{req.api_port}",
        role=req.role,
        network=NetworkConfig(
            bind_host="0.0.0.0" if req.role == NodeRole.WORKER else "127.0.0.1",
            api_port=req.api_port,
            rpc_port=req.rpc_port,
        ),
        peers=peers,
        inference=inference,
    )


def write_runtime_config(config: NodeConfig, runtime_dir: Path) -> Path:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    path = runtime_dir / f"{config.node_id}.yaml"
    data = config.model_dump(mode="json")
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
    return path
