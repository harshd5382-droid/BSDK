"""Tests for Generation 2 resource advertisement."""

from __future__ import annotations

from daios_protocol.config import NodeConfig, ResourceCapsConfig
from daios_protocol.health import ResourceAdvertisement

from daios_node.resources import (
    gather_advertisement,
    gather_resources,
    score_peer_for_placement,
    should_refuse_work,
)


def test_gather_resources_shape():
    res = gather_resources()
    assert res.cpu_count is not None
    assert res.ram_total_gb is not None


def test_gather_advertisement_shape():
    config = NodeConfig.model_validate({"node_id": "n1", "role": "worker"})
    ad = gather_advertisement(config)
    assert ad.node_id == "n1"
    assert ad.ram_total_gb is not None
    assert ad.ram_available_gb is not None


def test_score_peer_for_placement_prefers_memory():
    high_mem = ResourceAdvertisement(
        node_id="a",
        ram_available_gb=32.0,
        cpu_percent=10.0,
    )
    low_mem = ResourceAdvertisement(
        node_id="b",
        ram_available_gb=2.0,
        cpu_percent=10.0,
    )
    assert score_peer_for_placement(high_mem) > score_peer_for_placement(low_mem)


def test_should_refuse_work_cpu_cap():
    ad = ResourceAdvertisement(node_id="a", cpu_percent=95.0)
    caps = ResourceCapsConfig(max_cpu_percent=80.0)
    assert should_refuse_work(ad, caps) is True


def test_should_refuse_work_within_caps():
    ad = ResourceAdvertisement(node_id="a", cpu_percent=50.0, ram_available_gb=8.0)
    caps = ResourceCapsConfig(max_cpu_percent=80.0)
    assert should_refuse_work(ad, caps) is False
