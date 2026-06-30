"""Derive per-node AI model utilization for the dashboard."""

from __future__ import annotations

from pathlib import Path

from daios_protocol.config import NodeConfig
from daios_protocol.health import InferenceStatus, ModelUsage, ProcessState


def gather_model_usage(
    config: NodeConfig,
    inference: InferenceStatus,
    active_inference_requests: int,
    inbound_rpc_clients: int,
) -> ModelUsage:
    model_name = Path(inference.model_path).name if inference.model_path else None

    if config.runs_coordinator:
        if inference.llama_server != ProcessState.RUNNING:
            return ModelUsage(
                status="offline",
                usage_percent=0.0,
                detail="Model not loaded",
                model_name=model_name,
            )
        if active_inference_requests > 0:
            return ModelUsage(
                status="active",
                usage_percent=100.0,
                detail="Generating",
                model_name=model_name,
            )
        return ModelUsage(
            status="idle",
            usage_percent=0.0,
            detail="Ready",
            model_name=model_name,
        )

    if config.runs_rpc_server:
        if inference.rpc_server != ProcessState.RUNNING:
            return ModelUsage(
                status="offline",
                usage_percent=0.0,
                detail="RPC server offline",
                model_name=None,
            )
        if inbound_rpc_clients > 0:
            return ModelUsage(
                status="active",
                usage_percent=100.0,
                detail="Serving inference",
                model_name=None,
            )
        return ModelUsage(
            status="idle",
            usage_percent=0.0,
            detail="Waiting for coordinator",
            model_name=None,
        )

    return ModelUsage(
        status="offline",
        usage_percent=0.0,
        detail="N/A",
        model_name=None,
    )
