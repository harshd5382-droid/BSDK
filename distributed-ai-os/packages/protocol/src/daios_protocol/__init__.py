"""Shared configuration and protocol types for Distributed AI OS."""

from daios_protocol.config import (
    InferenceConfig,
    NetworkConfig,
    NodeConfig,
    NodeRole,
    PeerConfig,
    load_config,
)
from daios_protocol.health import ClusterStatus, NodeHealth, PeerStatus

__all__ = [
    "ClusterStatus",
    "InferenceConfig",
    "NetworkConfig",
    "NodeConfig",
    "NodeHealth",
    "NodeRole",
    "PeerConfig",
    "PeerStatus",
    "load_config",
]
