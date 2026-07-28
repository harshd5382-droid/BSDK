"""Resource advertisement for Generation 2 cluster membership."""

from __future__ import annotations

import logging
import platform
import shutil
import threading
import time as _time
from datetime import datetime, timezone

import psutil

from daios_node.platform_utils import system_disk_root
from daios_protocol.config import NodeConfig, ResourceCapsConfig
from daios_protocol.health import (
    GpuInfo,
    NodeCapabilities,
    ResourceAdvertisement,
    ResourceUsage,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CPU % cache — psutil.cpu_percent(interval=None) compares against the last
# call in this process.  When multiple concurrent callers (dashboard poll,
# membership heartbeat, /health ping from the coordinator) all fire within
# milliseconds of each other the measurement window becomes < 100 ms, which
# produces wildly noisy readings.  We cache the value for 1 s so every
# caller within that window shares one well-sampled measurement.
# ---------------------------------------------------------------------------
_cpu_lock: threading.Lock = threading.Lock()
_cpu_value: float = 0.0
_cpu_ts: float = 0.0
_CPU_TTL: float = 1.0


def _get_cpu_percent() -> float:
    global _cpu_value, _cpu_ts
    now = _time.monotonic()
    with _cpu_lock:
        if now - _cpu_ts >= _CPU_TTL:
            _cpu_value = psutil.cpu_percent(interval=None)
            _cpu_ts = now
        return _cpu_value


def gather_resources() -> ResourceUsage:
    """Snapshot live CPU / RAM usage for this machine."""
    mem = psutil.virtual_memory()
    return ResourceUsage(
        cpu_percent=round(_get_cpu_percent(), 1),
        cpu_count=psutil.cpu_count(logical=True),
        ram_used_gb=round((mem.total - mem.available) / (1024**3), 2),
        ram_total_gb=round(mem.total / (1024**3), 2),
        ram_percent=mem.percent,
    )


# nvidia-smi is an external process; heartbeats, health checks, and capability
# reports may all ask within the same second. Cache briefly like the CPU value.
_gpu_lock: threading.Lock = threading.Lock()
_gpu_value: GpuInfo | None = None
_gpu_ts: float = 0.0
_GPU_TTL: float = 2.0


def _gather_gpu_info_cached() -> GpuInfo | None:
    global _gpu_value, _gpu_ts
    now = _time.monotonic()
    with _gpu_lock:
        if now - _gpu_ts >= _GPU_TTL:
            _gpu_value = _gather_gpu_info()
            _gpu_ts = now
        return _gpu_value


def _gather_gpu_info() -> GpuInfo | None:
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            # Polled frequently — must never flash a console from a windowed exe.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        parts = [p.strip() for p in result.stdout.strip().split(",")]
        if len(parts) < 4:
            return None
        return GpuInfo(
            name=parts[0],
            vram_total_gb=round(float(parts[1]) / 1024, 2),
            vram_used_gb=round(float(parts[2]) / 1024, 2),
            utilization_percent=float(parts[3]),
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _gather_battery() -> float | None:
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return None
        return battery.percent
    except (AttributeError, OSError):
        return None


def _gather_user_idle_seconds() -> float | None:
    """Seconds the interactive user has been idle.

    There is no portable way to read this, and the previous implementation
    returned ``psutil.cpu_times().idle`` — cumulative CPU idle time since boot
    across all cores, which is a different quantity entirely (it grows without
    bound on an idle machine and is often larger than the uptime). Reporting
    None is honest; a wrong number here would skew placement decisions.
    """
    return None


def _caps_dict(caps: ResourceCapsConfig) -> dict[str, float]:
    result: dict[str, float] = {}
    if caps.max_cpu_percent is not None:
        result["max_cpu_percent"] = caps.max_cpu_percent
    if caps.max_ram_gb is not None:
        result["max_ram_gb"] = caps.max_ram_gb
    if caps.max_gpu_percent is not None:
        result["max_gpu_percent"] = caps.max_gpu_percent
    return result


def _cpu_model() -> str | None:
    try:
        name = platform.processor() or platform.uname().processor or platform.machine()
        return name or None
    except OSError:
        return None


def gather_capabilities(
    config: NodeConfig,
    rpc_ready: bool | None = None,
    rpc_devices: list[str] | None = None,
) -> NodeCapabilities:
    """Snapshot this node's hardware + inference-backend capabilities.

    ``gpu_available`` means GPU *hardware* was detected (via nvidia-smi);
    whether the llama.cpp binaries can actually use it is a separate,
    measured question answered by ``rpc_devices`` / the coordinator's device
    probe. Every metric degrades to None when unavailable.
    """
    mem = psutil.virtual_memory()
    gpu = _gather_gpu_info_cached()
    notes: list[str] = []
    if gpu is None:
        notes.append("no GPU detected (nvidia-smi unavailable or reported no device)")
    elif rpc_devices is not None and not any(
        d.upper().startswith(("CUDA", "ROCM", "HIP", "VULKAN", "METAL", "SYCL", "GPU"))
        for d in rpc_devices
    ):
        notes.append(
            "GPU hardware present but the RPC server binary exposes no GPU device "
            "(CPU-only build?)"
        )

    vram_available = None
    if gpu and gpu.vram_total_gb is not None and gpu.vram_used_gb is not None:
        vram_available = round(gpu.vram_total_gb - gpu.vram_used_gb, 2)

    return NodeCapabilities(
        node_id=config.node_id,
        ram_total_gb=round(mem.total / (1024**3), 2),
        ram_available_gb=round(mem.available / (1024**3), 2),
        cpu_model=_cpu_model(),
        cpu_cores=psutil.cpu_count(logical=True),
        gpu_available=gpu is not None,
        gpu_backend="cuda" if gpu is not None else None,
        gpu_name=gpu.name if gpu else None,
        gpu_vram_total_gb=gpu.vram_total_gb if gpu else None,
        gpu_vram_available_gb=vram_available,
        rpc_ready=rpc_ready,
        rpc_host=config.network.bind_host,
        rpc_port=config.network.rpc_port if config.runs_rpc_server else None,
        rpc_devices=rpc_devices or [],
        notes=notes,
    )


def gather_advertisement(
    config: NodeConfig,
    current_workload: int = 0,
    queue_depth: int = 0,
    rtt_ms: dict[str, float] | None = None,
    capabilities: NodeCapabilities | None = None,
) -> ResourceAdvertisement:
    """Build a full resource advertisement for gossip."""
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage(system_disk_root())
    cpu_count = psutil.cpu_count(logical=True) or 1
    # Must go through the cache: psutil.cpu_percent(interval=None) measures
    # against the *last call in this process*, so calling it raw here resets
    # the window for gather_resources() and both readings become noise. That
    # noise feeds placement scores, which decide where tensors land.
    cpu_percent = _get_cpu_percent()
    available_cores = max(1, int(cpu_count * (1 - cpu_percent / 100)))

    return ResourceAdvertisement(
        node_id=config.node_id,
        cpu_percent=round(cpu_percent, 1),
        cpu_available_cores=available_cores,
        ram_total_gb=round(mem.total / (1024**3), 2),
        ram_available_gb=round(mem.available / (1024**3), 2),
        gpu=_gather_gpu_info_cached(),
        disk_free_gb=round(disk.free / (1024**3), 2),
        bandwidth_mbps=None,
        rtt_ms=rtt_ms or {},
        thermal_state=None,
        battery_percent=_gather_battery(),
        user_idle_seconds=_gather_user_idle_seconds(),
        configured_caps=_caps_dict(config.resource_caps),
        current_workload=current_workload,
        queue_depth=queue_depth,
        capabilities=capabilities,
        timestamp=datetime.now(timezone.utc),
    )


def score_peer_for_placement(ad: ResourceAdvertisement, rtt_ms: float = 0.0) -> float:
    """Greedy placement score: higher is better (Gen 2)."""
    free_mem = ad.ram_available_gb or 0.0
    free_vram = 0.0
    if ad.gpu and ad.gpu.vram_total_gb and ad.gpu.vram_used_gb is not None:
        free_vram = ad.gpu.vram_total_gb - ad.gpu.vram_used_gb
    cpu_penalty = (ad.cpu_percent or 0.0) / 100.0
    load_penalty = ad.current_workload * 0.1
    latency_bonus = 1.0 / (1.0 + rtt_ms / 100.0)
    return free_mem + free_vram * 2.0 + latency_bonus - cpu_penalty - load_penalty


def should_refuse_work(ad: ResourceAdvertisement, caps: ResourceCapsConfig) -> bool:
    """Return True if this node should refuse new work."""
    if caps.max_cpu_percent is not None and (ad.cpu_percent or 0) > caps.max_cpu_percent:
        return True
    if caps.max_ram_gb is not None and (ad.ram_available_gb or 0) < caps.max_ram_gb * 0.1:
        return True
    return False
