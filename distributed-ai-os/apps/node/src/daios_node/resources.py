"""Resource advertisement for Generation 2 cluster membership."""

from __future__ import annotations

import logging
import shutil
import threading
import time as _time
from datetime import datetime, timezone

import psutil

from daios_protocol.config import NodeConfig, ResourceCapsConfig
from daios_protocol.health import GpuInfo, ResourceAdvertisement, ResourceUsage

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


def _gather_gpu_info() -> GpuInfo | None:
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
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
    try:
        idle = psutil.cpu_times().idle
        return float(idle) if idle else None
    except (AttributeError, OSError):
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


def gather_advertisement(
    config: NodeConfig,
    current_workload: int = 0,
    rtt_ms: dict[str, float] | None = None,
) -> ResourceAdvertisement:
    """Build a full resource advertisement for gossip."""
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    cpu_count = psutil.cpu_count(logical=True) or 1
    cpu_percent = psutil.cpu_percent(interval=None)
    available_cores = max(1, int(cpu_count * (1 - cpu_percent / 100)))

    return ResourceAdvertisement(
        node_id=config.node_id,
        cpu_percent=round(cpu_percent, 1),
        cpu_available_cores=available_cores,
        ram_total_gb=round(mem.total / (1024**3), 2),
        ram_available_gb=round(mem.available / (1024**3), 2),
        gpu=_gather_gpu_info(),
        disk_free_gb=round(disk.free / (1024**3), 2),
        bandwidth_mbps=None,
        rtt_ms=rtt_ms or {},
        thermal_state=None,
        battery_percent=_gather_battery(),
        user_idle_seconds=_gather_user_idle_seconds(),
        configured_caps=_caps_dict(config.resource_caps),
        current_workload=current_workload,
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
