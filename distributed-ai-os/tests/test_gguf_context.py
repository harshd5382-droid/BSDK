"""Tests for GGUF context metadata parsing."""

from __future__ import annotations

import struct
from pathlib import Path

from daios_launcher.config_gen import (
    DISTRIBUTED_CONTEXT_CAP,
    INFERENCE_CONTEXT_CAP,
    StartRequest,
    build_node_config,
)
from daios_launcher.gguf_context import GGUF_MAGIC, infer_context_size, read_gguf_metadata
from daios_protocol.config import NodeRole


def _encode_string(value: str) -> bytes:
    data = value.encode("utf-8")
    return struct.pack("<Q", len(data)) + data


def _encode_kv_string(key: str, value: str) -> bytes:
    return _encode_string(key) + struct.pack("<I", 8) + _encode_string(value)


def _encode_kv_uint32(key: str, value: int) -> bytes:
    return _encode_string(key) + struct.pack("<I", 4) + struct.pack("<I", value)


def write_test_gguf(
    path: Path,
    *,
    architecture: str = "qwen2",
    context_length: int = 32768,
) -> None:
    header = struct.pack("<IIQQ", GGUF_MAGIC, 2, 0, 2)
    body = _encode_kv_string("general.architecture", architecture) + _encode_kv_uint32(
        f"{architecture}.context_length",
        context_length,
    )
    path.write_bytes(header + body)


def test_read_gguf_metadata(tmp_path: Path):
    model = tmp_path / "model.gguf"
    write_test_gguf(model, architecture="llama", context_length=8192)

    metadata = read_gguf_metadata(model)
    assert metadata["general.architecture"] == "llama"
    assert metadata["llama.context_length"] == 8192


def test_infer_context_size(tmp_path: Path):
    model = tmp_path / "model.gguf"
    write_test_gguf(model, context_length=131072)

    assert infer_context_size(model) == 131072
    assert infer_context_size(tmp_path / "missing.gguf") is None


def test_build_node_config_uses_model_context(tmp_path: Path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model = models_dir / "test-model.gguf"
    # Native context at/above the cap is clamped. With a manual peer this is a
    # distributed coordinator → DISTRIBUTED_CONTEXT_CAP, not full 128k.
    write_test_gguf(model, context_length=131072)

    req = StartRequest(
        role=NodeRole.COORDINATOR,
        peer_host="192.168.1.42",
        model_path="models/test-model.gguf",
        backend="llama.cpp",
    )
    config = build_node_config(req, project_root=tmp_path)
    assert config.inference.context_size == DISTRIBUTED_CONTEXT_CAP


def test_build_node_config_solo_coordinator_keeps_large_context(tmp_path: Path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model = models_dir / "solo.gguf"
    write_test_gguf(model, context_length=131072)

    req = StartRequest(
        role=NodeRole.COORDINATOR,
        model_path="models/solo.gguf",
        backend="llama.cpp",
    )
    config = build_node_config(req, project_root=tmp_path)
    assert config.inference.context_size == INFERENCE_CONTEXT_CAP


def test_build_node_config_mock_backend_uses_auto_context(tmp_path: Path):
    req = StartRequest(
        role=NodeRole.COORDINATOR,
        peer_host="192.168.1.42",
        backend="mock",
    )
    config = build_node_config(req, project_root=tmp_path)
    assert config.inference.context_size == 0
