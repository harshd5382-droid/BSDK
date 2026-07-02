"""DistributionConfig schema validation and backward compatibility."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from daios_protocol.config import DistributionConfig, NodeConfig, load_config

_EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_distribution_absent_by_default():
    config = NodeConfig.model_validate(
        {"node_id": "n1", "role": "coordinator", "inference": {"backend": "mock"}}
    )
    assert config.inference.distribution is None


@pytest.mark.parametrize(
    "example",
    sorted(p.relative_to(_EXAMPLES) for p in _EXAMPLES.rglob("*.yaml")),
    ids=str,
)
def test_all_example_yaml_files_load(example):
    load_config(_EXAMPLES / example)


@pytest.mark.parametrize(
    "example",
    [
        "two-node/coordinator.yaml",
        "two-node/worker.yaml",
        "two-node-discovered/coordinator-mdns.yaml",
    ],
)
def test_pre_distribution_examples_stay_legacy(example):
    config = load_config(_EXAMPLES / example)
    assert config.inference.distribution is None


def test_distribution_block_parses_suggested_shape():
    raw = yaml.safe_load(
        """
node_id: coord
role: coordinator
inference:
  backend: llama.cpp
  model_path: models/example.gguf
  distribution:
    policy: auto
    coordinator_reserve_ram_gb: 4
    coordinator_reserve_vram_gb: 1
    worker_reserve_ram_gb: 2
    worker_reserve_vram_gb: 0.5
    minimum_worker_vram_gb: 1
    prefer_worker_devices: true
    manual_allocations:
      worker-node-1:
        weight: 0.7
      coordinator-node:
        weight: 0.3
"""
    )
    config = NodeConfig.model_validate(raw)
    dist = config.inference.distribution
    assert dist is not None
    assert dist.policy == "auto"
    assert dist.minimum_worker_vram_gb == 1
    assert dist.manual_allocations["worker-node-1"].weight == 0.7


def test_manual_allocations_accept_plain_floats():
    dist = DistributionConfig.model_validate(
        {"policy": "manual", "manual_allocations": {"w1": 0.7, "c1": 0.3}}
    )
    assert dist.manual_allocations["w1"].weight == 0.7


def test_invalid_policy_rejected():
    with pytest.raises(ValueError, match="policy"):
        DistributionConfig.model_validate({"policy": "everything-on-the-toaster"})


def test_manual_policy_requires_allocations():
    with pytest.raises(ValueError, match="manual_allocations"):
        DistributionConfig.model_validate({"policy": "manual"})


def test_negative_reserve_rejected():
    with pytest.raises(ValueError):
        DistributionConfig.model_validate({"worker_reserve_ram_gb": -1})


def test_negative_manual_weight_rejected():
    with pytest.raises(ValueError):
        DistributionConfig.model_validate(
            {"policy": "manual", "manual_allocations": {"w1": -0.5}}
        )
