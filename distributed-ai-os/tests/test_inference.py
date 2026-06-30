"""Tests for daios_node inference subprocess command building."""

from __future__ import annotations

from unittest.mock import patch

from daios_protocol.config import InferenceConfig, NetworkConfig, NodeConfig, NodeRole
from daios_node.inference import InferenceManager


def _worker_config(threads: int | None = 4) -> NodeConfig:
    return NodeConfig(
        node_id="worker-test",
        role=NodeRole.WORKER,
        network=NetworkConfig(bind_host="127.0.0.1", rpc_port=50052),
        inference=InferenceConfig(
            backend="llama.cpp",
            rpc_server_bin="ggml-rpc-server",
            threads=threads,
            rpc_cache=True,
        ),
    )


def test_rpc_server_command_includes_threads():
    manager = InferenceManager(_worker_config(threads=5))
    with patch("daios_node.inference.subprocess.Popen"):
        manager._start_rpc_server()
    assert manager.rpc_server is not None
    cmd = manager.rpc_server.command
    assert "-t" in cmd
    assert cmd[cmd.index("-t") + 1] == "5"


def test_rpc_server_command_omits_threads_when_unset():
    manager = InferenceManager(_worker_config(threads=None))
    with patch("daios_node.inference.subprocess.Popen"):
        manager._start_rpc_server()
    assert manager.rpc_server is not None
    assert "-t" not in manager.rpc_server.command
