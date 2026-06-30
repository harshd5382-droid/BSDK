"""Tests for workload balancing (tensor_split / worker_share)."""

from __future__ import annotations

from daios_launcher.config_gen import StartRequest, build_node_config, compute_tensor_split
from daios_protocol.config import NodeRole


def test_compute_tensor_split_single_worker():
    assert compute_tensor_split(80) == "20,80"
    assert compute_tensor_split(50) == "50,50"


def test_compute_tensor_split_clamps():
    assert compute_tensor_split(150) == "0,100"
    assert compute_tensor_split(-10) == "100,0"


def test_compute_tensor_split_multiple_workers():
    # Worker share split evenly across two workers, local first.
    assert compute_tensor_split(80, 2) == "20,40,40"


def test_worker_share_derives_tensor_split():
    req = StartRequest(
        role=NodeRole.COORDINATOR,
        peer_host="192.168.1.42",
        backend="mock",
        worker_share=80,
    )
    config = build_node_config(req, node_id="coord")
    assert config.inference.tensor_split == "20,80"


def test_explicit_tensor_split_overrides_share():
    req = StartRequest(
        role=NodeRole.COORDINATOR,
        peer_host="192.168.1.42",
        backend="mock",
        worker_share=80,
        tensor_split="10,90",
    )
    config = build_node_config(req, node_id="coord")
    assert config.inference.tensor_split == "10,90"


def test_worker_share_ignored_for_worker_role():
    req = StartRequest(role=NodeRole.WORKER, backend="mock", worker_share=80)
    config = build_node_config(req, node_id="worker")
    assert config.inference.tensor_split is None


def test_no_balancing_by_default():
    req = StartRequest(role=NodeRole.COORDINATOR, peer_host="192.168.1.42", backend="mock")
    config = build_node_config(req, node_id="coord")
    assert config.inference.tensor_split is None
