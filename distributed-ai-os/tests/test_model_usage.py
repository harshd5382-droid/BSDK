"""Tests for model usage reporting."""

from daios_protocol.config import InferenceConfig, NetworkConfig, NodeConfig, NodeRole
from daios_protocol.health import InferenceStatus, ProcessState

from daios_node.model_usage import gather_model_usage


def _coordinator_config() -> NodeConfig:
    return NodeConfig(
        node_id="coord",
        role=NodeRole.COORDINATOR,
        network=NetworkConfig(api_port=8000, rpc_port=50052),
        inference=InferenceConfig(backend="llama.cpp", model_path="/models/qwen.gguf"),
    )


def _worker_config() -> NodeConfig:
    return NodeConfig(
        node_id="worker",
        role=NodeRole.WORKER,
        network=NetworkConfig(api_port=8001, rpc_port=50053),
    )


def test_coordinator_idle_when_model_loaded():
    config = _coordinator_config()
    inference = InferenceStatus(
        backend="llama.cpp",
        llama_server=ProcessState.RUNNING,
        model_path="/models/qwen.gguf",
    )
    usage = gather_model_usage(config, inference, active_inference_requests=0, inbound_rpc_clients=0)
    assert usage.status == "idle"
    assert usage.usage_percent == 0.0
    assert usage.model_name == "qwen.gguf"


def test_coordinator_active_during_inference():
    config = _coordinator_config()
    inference = InferenceStatus(
        backend="llama.cpp",
        llama_server=ProcessState.RUNNING,
        model_path="/models/qwen.gguf",
    )
    usage = gather_model_usage(config, inference, active_inference_requests=1, inbound_rpc_clients=0)
    assert usage.status == "active"
    assert usage.usage_percent == 100.0


def test_worker_active_when_serving_rpc():
    config = _worker_config()
    inference = InferenceStatus(backend="llama.cpp", rpc_server=ProcessState.RUNNING)
    usage = gather_model_usage(config, inference, active_inference_requests=0, inbound_rpc_clients=1)
    assert usage.status == "active"
    assert usage.detail == "Serving inference"
