"""Tests for tensor-placement allocation and command redaction."""

from __future__ import annotations

import pytest

from daios_node.allocation import (
    ProbedDevice,
    classify_device,
    compute_allocation,
    parse_device_listing,
    redact_command,
)
from daios_protocol.config import DistributionConfig
from daios_protocol.health import NodeCapabilities

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_LIST_DEVICES_OUTPUT = """\
ggml_cuda_init: found 1 CUDA devices:
  Device 0: NVIDIA GeForce RTX 4090, compute capability 8.9, VMM: yes
Available devices:
  CUDA0: NVIDIA GeForce RTX 4090 (24564 MiB, 23906 MiB free)
  RPC[10.0.0.2:50052]: RPC Device (16384 MiB, 15872 MiB free)
"""

_RPC_BANNER = """\
Starting RPC server v3.0.0
  endpoint       : 0.0.0.0:50052
  local cache    : n/a
Devices:
  CUDA0: NVIDIA GeForce RTX 5090 (32109 MiB, 31588 MiB free)
"""


def test_parse_device_listing():
    devices = parse_device_listing(_LIST_DEVICES_OUTPUT)
    assert [d.name for d in devices] == ["CUDA0", "RPC[10.0.0.2:50052]"]
    assert devices[0].total_mib == 24564
    assert devices[1].free_mib == 15872


def test_parse_rpc_server_banner():
    devices = parse_device_listing(_RPC_BANNER)
    assert [d.name for d in devices] == ["CUDA0"]


def test_parse_garbage_returns_empty():
    assert parse_device_listing("no devices here\nrandom: text") == []


def test_classify_device():
    assert classify_device("CUDA0") == ("local_gpu", None)
    assert classify_device("Vulkan1") == ("local_gpu", None)
    assert classify_device("RPC[10.0.0.2:50052]") == ("rpc", "10.0.0.2:50052")
    assert classify_device("Weird0") == ("unknown", None)


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_redact_command_masks_secret_flag_values():
    cmd = ["llama-server", "--api-key", "s3cret", "-ngl", "99"]
    assert redact_command(cmd) == ["llama-server", "--api-key", "***", "-ngl", "99"]


def test_redact_command_masks_inline_secrets():
    cmd = ["run", "CLUSTER_TOKEN=abc123", "--rpc", "10.0.0.2:50052"]
    assert redact_command(cmd) == ["run", "CLUSTER_TOKEN=***", "--rpc", "10.0.0.2:50052"]


def test_redact_command_leaves_normal_args():
    cmd = ["llama-server", "-m", "model.gguf", "--tensor-split", "0.5,0.5"]
    assert redact_command(cmd) == cmd


# ---------------------------------------------------------------------------
# Allocation policies
# ---------------------------------------------------------------------------


def _gpu_worker_caps(node_id: str) -> NodeCapabilities:
    return NodeCapabilities(node_id=node_id, gpu_available=True, rpc_devices=["CUDA0"])


def _cpu_worker_caps(node_id: str) -> NodeCapabilities:
    return NodeCapabilities(node_id=node_id, gpu_available=False, rpc_devices=["CPU"])


def _dist(**overrides) -> DistributionConfig:
    defaults = {
        "policy": "balanced",
        "coordinator_reserve_ram_gb": 0.0,
        "coordinator_reserve_vram_gb": 0.0,
        "worker_reserve_ram_gb": 0.0,
        "worker_reserve_vram_gb": 0.0,
    }
    defaults.update(overrides)
    return DistributionConfig.model_validate(defaults)


def _rpc_dev(host: str, free_gib: float, total_gib: float | None = None) -> ProbedDevice:
    total = total_gib if total_gib is not None else free_gib
    return ProbedDevice(
        name=f"RPC[{host}:50052]",
        description="RPC Device",
        total_mib=total * 1024,
        free_mib=free_gib * 1024,
    )


def _cuda_dev(free_gib: float, total_gib: float | None = None) -> ProbedDevice:
    total = total_gib if total_gib is not None else free_gib
    return ProbedDevice(
        name="CUDA0", description="Local GPU", total_mib=total * 1024, free_mib=free_gib * 1024
    )


def test_balanced_equal_capacity_nodes_split_evenly():
    result = compute_allocation(
        _dist(),
        [_rpc_dev("10.0.0.2", 8), _rpc_dev("10.0.0.3", 8)],
        "coord",
    )
    assert result.tensor_split == "0.5000,0.5000"
    assert all(d.share_percent == 50.0 for d in result.devices)


def test_balanced_unequal_capacity_is_proportional_not_5050():
    result = compute_allocation(
        _dist(),
        [_rpc_dev("10.0.0.2", 8), _rpc_dev("10.0.0.3", 24)],
        "coord",
    )
    small, big = result.devices
    assert small.share_percent == 25.0
    assert big.share_percent == 75.0
    assert result.tensor_split == "0.2500,0.7500"


def test_auto_discounts_cpu_backed_worker():
    caps = {
        "10.0.0.2": _gpu_worker_caps("w-gpu"),
        "10.0.0.3": _cpu_worker_caps("w-cpu"),
    }
    result = compute_allocation(
        _dist(policy="auto", cpu_device_discount=0.5),
        [_rpc_dev("10.0.0.2", 8), _rpc_dev("10.0.0.3", 8)],
        "coord",
        worker_caps=caps,
    )
    gpu_dev, cpu_dev = result.devices
    assert gpu_dev.memory_type == "vram"
    assert cpu_dev.memory_type == "ram"
    assert gpu_dev.weight == pytest.approx(2 * cpu_dev.weight)


def test_auto_discounts_high_latency_worker():
    caps = {
        "10.0.0.2": _gpu_worker_caps("w-near"),
        "10.0.0.3": _gpu_worker_caps("w-far"),
    }
    result = compute_allocation(
        _dist(policy="auto", latency_discount_ms=200.0),
        [_rpc_dev("10.0.0.2", 8), _rpc_dev("10.0.0.3", 8)],
        "coord",
        worker_caps=caps,
        rtt_ms_by_host={"10.0.0.3": 200.0},
    )
    near, far = result.devices
    assert far.weight == pytest.approx(near.weight / 2)


def test_worker_preferred_scales_down_coordinator_gpu():
    caps = {"10.0.0.2": _gpu_worker_caps("w1")}
    result = compute_allocation(
        _dist(policy="worker_preferred", coordinator_weight_scale=0.2),
        [_cuda_dev(10), _rpc_dev("10.0.0.2", 10)],
        "coord",
        worker_caps=caps,
    )
    local, remote = result.devices
    assert local.kind == "local_gpu"
    assert local.weight == pytest.approx(remote.weight * 0.2)
    assert remote.share_percent > local.share_percent


def test_manual_allocation_by_node_id_and_host():
    caps = {"10.0.0.2": _gpu_worker_caps("worker-node-1")}
    result = compute_allocation(
        _dist(
            policy="manual",
            manual_allocations={"worker-node-1": 0.7, "coord": {"weight": 0.3}},
        ),
        [_cuda_dev(10), _rpc_dev("10.0.0.2", 10)],
        "coord",
        worker_caps=caps,
    )
    local, remote = result.devices
    assert local.weight == pytest.approx(0.3)
    assert remote.weight == pytest.approx(0.7)
    assert result.tensor_split == "0.3000,0.7000"


def test_manual_allocation_excludes_unlisted_nodes():
    result = compute_allocation(
        _dist(policy="manual", manual_allocations={"coord": 1.0}),
        [_cuda_dev(10), _rpc_dev("10.0.0.2", 10)],
        "coord",
    )
    local, remote = result.devices
    assert remote.excluded_reason == "not listed in manual_allocations"
    assert remote.weight == 0.0
    assert local.share_percent == 100.0


def test_worker_with_insufficient_memory_after_reserve_is_excluded():
    result = compute_allocation(
        _dist(worker_reserve_ram_gb=4.0),
        [_rpc_dev("10.0.0.2", 2), _rpc_dev("10.0.0.3", 10)],
        "coord",
    )
    small, big = result.devices
    assert small.excluded_reason is not None
    assert "reserve" in small.excluded_reason
    assert big.share_percent == 100.0


def test_minimum_worker_vram_excludes_small_gpu():
    caps = {"10.0.0.2": _gpu_worker_caps("w1"), "10.0.0.3": _gpu_worker_caps("w2")}
    result = compute_allocation(
        _dist(minimum_worker_vram_gb=4.0),
        [_rpc_dev("10.0.0.2", 2), _rpc_dev("10.0.0.3", 24)],
        "coord",
        worker_caps=caps,
    )
    small, big = result.devices
    assert "minimum_worker_vram_gb" in (small.excluded_reason or "")
    assert big.share_percent == 100.0


def test_all_devices_excluded_falls_back_to_default_split():
    result = compute_allocation(
        _dist(worker_reserve_ram_gb=100.0),
        [_rpc_dev("10.0.0.2", 8), _rpc_dev("10.0.0.3", 8)],
        "coord",
    )
    assert result.tensor_split is None
    assert result.fallback_reason is not None


def test_single_device_needs_no_tensor_split():
    result = compute_allocation(_dist(), [_cuda_dev(24)], "coord")
    assert result.tensor_split is None
    assert result.fallback_reason is None
    assert result.devices[0].share_percent == 100.0


def test_unknown_worker_capabilities_handled_gracefully():
    # No capability advertisement at all: memory type unknown, RAM reserve used.
    result = compute_allocation(
        _dist(worker_reserve_ram_gb=1.0, worker_reserve_vram_gb=0.0),
        [_rpc_dev("10.0.0.2", 8)],
        "coord",
    )
    dev = result.devices[0]
    assert dev.memory_type == "unknown"
    assert dev.reserve_gb == 1.0
    assert dev.usable_gb == pytest.approx(7.0)
