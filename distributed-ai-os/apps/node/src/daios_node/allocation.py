"""Tensor-placement allocation for distributed llama.cpp inference.

What GGML RPC can and cannot distribute (llama.cpp `tools/rpc`):

- llama.cpp splits model *weights and the KV cache* across all GPU-class
  devices — local GPUs plus every device exposed by each `ggml-rpc-server`
  in ``--rpc``. The default split is proportional to each device's free
  memory; ``--tensor-split`` overrides the proportions.
- Compute follows tensor placement (pipeline-parallel layer split): prompt
  processing and token generation for a layer run on the device that holds
  it, including remote RPC devices.
- An RPC device is whatever backend the *remote* binary was built with: a
  CPU-only ``ggml-rpc-server`` exposes one CPU device backed by system RAM;
  a CUDA build exposes the remote GPU(s) backed by VRAM. System RAM and GPU
  VRAM are distinct resources and are never interchangeable.
- The coordinator always keeps: tokenization, sampling, logits/output
  readback, graph orchestration, and any layers not offloaded via ``-ngl``
  (those run on the coordinator CPU in system RAM).

This module computes per-device allocation weights from measured device
memory (via ``llama-server --list-devices``, which reports exactly what
llama.cpp itself sees, including RPC devices) plus advertised node
capabilities, and translates them into a ``--tensor-split`` value — the
only per-device placement control the bundled llama.cpp build supports.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field

from daios_protocol.config import DistributionConfig
from daios_protocol.health import DeviceAllocation, NodeCapabilities

logger = logging.getLogger(__name__)

_MIB = 1024.0  # MiB per GiB

# Flags whose *following value* is a secret. The launch commands BSDK builds
# never include secrets, but user-supplied extra_args might.
_SECRET_FLAGS = {
    "--api-key",
    "--api-key-file",
    "--hf-token",
    "--ssl-key-file",
    "--token",
}
_SECRET_INLINE = re.compile(r"(?i)^(?P<key>[^=]*(token|key|secret|password)[^=]*)=(?P<val>.+)$")

_GPU_DEVICE_PREFIXES = ("CUDA", "ROCM", "HIP", "VULKAN", "METAL", "SYCL", "GPU", "OPENCL")


def redact_command(command: list[str]) -> list[str]:
    """Mask secret values in a subprocess command for logs/diagnostics."""
    redacted: list[str] = []
    mask_next = False
    for arg in command:
        if mask_next:
            redacted.append("***")
            mask_next = False
            continue
        if arg.lower() in _SECRET_FLAGS:
            redacted.append(arg)
            mask_next = True
            continue
        match = _SECRET_INLINE.match(arg)
        if match:
            redacted.append(f"{match.group('key')}=***")
            continue
        redacted.append(arg)
    return redacted


@dataclass
class ProbedDevice:
    """One device as printed by ``llama-server --list-devices`` or the
    ``ggml-rpc-server`` startup banner (same line format)."""

    name: str
    description: str = ""
    total_mib: float | None = None
    free_mib: float | None = None


# "  CUDA0: NVIDIA GeForce RTX 4090 (24564 MiB, 23906 MiB free)"
_DEVICE_LINE = re.compile(
    r"^\s+(?P<name>\S+):\s+(?P<desc>.*?)\s*"
    r"\((?P<total>\d+)\s*MiB,\s*(?P<free>\d+)\s*MiB free\)\s*$"
)


def parse_device_listing(text: str) -> list[ProbedDevice]:
    """Parse device lines from llama.cpp output (list-devices / RPC banner)."""
    devices: list[ProbedDevice] = []
    for line in text.splitlines():
        match = _DEVICE_LINE.match(line)
        if match:
            devices.append(
                ProbedDevice(
                    name=match.group("name"),
                    description=match.group("desc"),
                    total_mib=float(match.group("total")),
                    free_mib=float(match.group("free")),
                )
            )
    return devices


def probe_llama_devices(
    binary: str,
    rpc_endpoints: list[str],
    timeout: float = 30.0,
) -> list[ProbedDevice] | None:
    """Run ``llama-server --list-devices [--rpc ...]`` and parse the result.

    This is ground truth: it reports the devices (and their memory) exactly
    as the bundled llama.cpp build will see them at launch, in the order
    ``--tensor-split`` values are applied. Returns None when the probe fails
    (missing binary, no ``--list-devices`` support, RPC connect failure).

    The process is short-lived and its output is fully drained by
    ``subprocess.run`` — the no-undrained-PIPE invariant applies to
    long-running servers, not to this bounded probe.
    """
    cmd = [binary, "--list-devices"]
    if rpc_endpoints:
        cmd.extend(["--rpc", ",".join(rpc_endpoints)])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Device probe failed (%s): %s", " ".join(redact_command(cmd)), exc)
        return None
    output = f"{result.stdout}\n{result.stderr}"
    devices = parse_device_listing(output)
    if not devices:
        logger.warning(
            "Device probe returned no parseable devices (exit=%s). Output tail: %s",
            result.returncode,
            output[-500:].strip(),
        )
        return None
    logger.info(
        "Device probe: %s",
        "; ".join(
            f"{d.name} ({d.description}, {d.total_mib:.0f} MiB total, {d.free_mib:.0f} MiB free)"
            for d in devices
        ),
    )
    return devices


_RPC_NAME = re.compile(r"^RPC\[(?P<endpoint>.+)\]$")


def classify_device(name: str) -> tuple[str, str | None]:
    """Return (kind, rpc_endpoint) for a llama.cpp device name."""
    match = _RPC_NAME.match(name)
    if match:
        return "rpc", match.group("endpoint")
    if name.upper().startswith(_GPU_DEVICE_PREFIXES):
        return "local_gpu", None
    return "unknown", None


@dataclass
class AllocationResult:
    devices: list[DeviceAllocation] = field(default_factory=list)
    tensor_split: str | None = None
    fallback_reason: str | None = None


def _worker_memory_type(caps: NodeCapabilities | None) -> str:
    """Whether a worker's RPC device is backed by VRAM or system RAM.

    Measured when the worker reports the devices its rpc-server binary
    exposes; otherwise unknown (treated conservatively as RAM for reserves).
    """
    if caps is None:
        return "unknown"
    if caps.rpc_devices:
        gpu_backed = any(d.upper().startswith(_GPU_DEVICE_PREFIXES) for d in caps.rpc_devices)
        return "vram" if gpu_backed else "ram"
    if not caps.gpu_available:
        return "ram"
    return "unknown"


def compute_allocation(
    dist: DistributionConfig,
    probed: list[ProbedDevice],
    local_node_id: str,
    worker_caps: dict[str, NodeCapabilities] | None = None,
    rtt_ms_by_host: dict[str, float] | None = None,
) -> AllocationResult:
    """Turn probed devices + capabilities into per-device weights.

    Weights are proportional shares in probe device order — exactly the
    order llama.cpp applies ``--tensor-split``. Never assumes equal splits:
    every policy starts from measured usable memory per device.
    """
    worker_caps = worker_caps or {}
    rtt_ms_by_host = rtt_ms_by_host or {}
    result = AllocationResult()

    for dev in probed:
        kind, endpoint = classify_device(dev.name)
        host = endpoint.rsplit(":", 1)[0] if endpoint else None
        caps = worker_caps.get(host) if host else None

        if kind == "rpc":
            memory_type = _worker_memory_type(caps)
            reserve = (
                dist.worker_reserve_vram_gb
                if memory_type == "vram"
                else dist.worker_reserve_ram_gb
            )
            node_id = caps.node_id if caps else None
        else:
            # Local device on the coordinator. list-devices only reports
            # GPU-class devices, so local means coordinator GPU (VRAM).
            memory_type = "vram" if kind == "local_gpu" else "unknown"
            reserve = (
                dist.coordinator_reserve_vram_gb
                if memory_type == "vram"
                else dist.coordinator_reserve_ram_gb
            )
            node_id = local_node_id

        free_gb = (dev.free_mib or 0.0) / _MIB
        total_gb = (dev.total_mib or 0.0) / _MIB
        usable = max(0.0, free_gb - reserve)

        alloc = DeviceAllocation(
            name=dev.name,
            kind=kind,
            endpoint=endpoint,
            node_id=node_id,
            memory_type=memory_type,
            total_gb=round(total_gb, 2),
            free_gb=round(free_gb, 2),
            reserve_gb=reserve,
            usable_gb=round(usable, 2),
            source="measured",
        )

        if usable <= 0.0:
            alloc.excluded_reason = (
                f"no usable memory after {reserve} GB reserve (free {free_gb:.1f} GB)"
            )
        elif (
            kind == "rpc"
            and memory_type == "vram"
            and dist.minimum_worker_vram_gb > 0
            and free_gb < dist.minimum_worker_vram_gb
        ):
            alloc.excluded_reason = (
                f"worker VRAM {free_gb:.1f} GB below minimum_worker_vram_gb "
                f"{dist.minimum_worker_vram_gb}"
            )
        result.devices.append(alloc)

    _apply_policy_weights(dist, result.devices, rtt_ms_by_host)

    total_weight = sum(d.weight for d in result.devices)
    if total_weight <= 0.0:
        result.fallback_reason = (
            "all devices excluded or zero-weighted; using llama.cpp default split"
        )
        for dev_alloc in result.devices:
            dev_alloc.share_percent = None
        return result

    for dev_alloc in result.devices:
        dev_alloc.share_percent = round(100.0 * dev_alloc.weight / total_weight, 1)

    if len(result.devices) > 1:
        parts = [f"{d.weight / total_weight:.4f}" for d in result.devices]
        if len(parts) == len(probed) and all(p != "nan" for p in parts):
            result.tensor_split = ",".join(parts)
        else:  # pragma: no cover - defensive
            result.fallback_reason = "allocation validation failed; using llama.cpp default"
    return result


def _apply_policy_weights(
    dist: DistributionConfig,
    devices: list[DeviceAllocation],
    rtt_ms_by_host: dict[str, float],
) -> None:
    for alloc in devices:
        if alloc.excluded_reason is not None:
            alloc.weight = 0.0
            continue

        weight = alloc.usable_gb

        if dist.policy == "balanced":
            pass  # proportional to usable memory only
        elif dist.policy in ("auto", "worker_preferred"):
            # Memory alone must not attract compute to a slow device.
            if alloc.memory_type != "vram":
                weight *= dist.cpu_device_discount
            if alloc.kind == "rpc":
                host = (alloc.endpoint or "").rsplit(":", 1)[0]
                rtt = rtt_ms_by_host.get(host)
                if rtt is not None and rtt > 0:
                    weight *= dist.latency_discount_ms / (dist.latency_discount_ms + rtt)
            if dist.policy == "worker_preferred" and alloc.kind != "rpc":
                weight *= dist.coordinator_weight_scale
        elif dist.policy == "manual":
            key_weight = _manual_weight(dist, alloc)
            if key_weight is None:
                alloc.excluded_reason = "not listed in manual_allocations"
                alloc.weight = 0.0
                continue
            # Node weight is split among that node's devices by usable memory.
            node_devices = [
                d
                for d in devices
                if d.excluded_reason is None
                and _manual_key(dist, d) == _manual_key(dist, alloc)
            ]
            node_usable = sum(d.usable_gb for d in node_devices) or 1.0
            weight = key_weight * (alloc.usable_gb / node_usable)

        alloc.weight = round(max(0.0, weight), 6)


def _manual_key(dist: DistributionConfig, alloc: DeviceAllocation) -> str | None:
    host = (alloc.endpoint or "").rsplit(":", 1)[0] if alloc.endpoint else None
    for key in dist.manual_allocations:
        if key == alloc.node_id or (host and key == host):
            return key
    return None


def _manual_weight(dist: DistributionConfig, alloc: DeviceAllocation) -> float | None:
    key = _manual_key(dist, alloc)
    if key is None:
        return None
    return dist.manual_allocations[key].weight
