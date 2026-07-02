"""Node scoring and ranking helpers for Generation 3 scheduler."""

from __future__ import annotations

from daios_protocol.config import ResourceCapsConfig
from daios_protocol.health import MemberInfo, MemberStatus
from daios_protocol.scheduling import Priority

from daios_node.resources import should_refuse_work


def _gpu_pressure(member: MemberInfo) -> float:
    ad = member.advertisement
    if not ad or not ad.gpu or ad.gpu.utilization_percent is None:
        return 0.0
    return max(0.0, min(1.0, ad.gpu.utilization_percent / 100.0))


def _ram_pressure(member: MemberInfo) -> float:
    ad = member.advertisement
    if not ad or not ad.ram_total_gb or ad.ram_available_gb is None:
        return 0.0
    used = max(0.0, ad.ram_total_gb - ad.ram_available_gb)
    return max(0.0, min(1.0, used / max(ad.ram_total_gb, 0.1)))


def _idle_bonus(member: MemberInfo) -> float:
    ad = member.advertisement
    if not ad:
        return 0.0
    if ad.user_idle_seconds is None:
        return 0.0
    return max(0.0, min(1.0, ad.user_idle_seconds / 600.0))


def score_node(
    member: MemberInfo,
    *,
    coordinator_node_id: str,
    priority: Priority,
    caps: ResourceCapsConfig,
) -> float:
    """Algorithm 1 score: higher is better, -inf means reject."""
    if member.status != MemberStatus.ALIVE:
        return float("-inf")
    ad = member.advertisement
    if ad and should_refuse_work(ad, caps):
        return float("-inf")

    s = 100.0
    cpu = ad.cpu_percent if ad and ad.cpu_percent is not None else 0.0
    workload = ad.current_workload if ad else 0
    rtt = ad.rtt_ms.get(coordinator_node_id, 0.0) if ad else 0.0
    battery = ad.battery_percent if ad else None
    thermal = ad.thermal_state if ad else None

    s -= cpu * 0.4
    s -= _ram_pressure(member) * 25.0
    s -= _gpu_pressure(member) * 30.0
    s -= rtt * 0.1
    s -= workload * 5.0

    if priority == Priority.INTERACTIVE:
        s += _idle_bonus(member) * 20.0
    if thermal == "throttling":
        s -= 50.0
    if battery is not None and battery < 20:
        s -= 40.0
    return s


def vram_fit(member: MemberInfo, model_size_gb: float | None) -> bool:
    """Algorithm 5 VRAM fit. Unknown values pass through."""
    if model_size_gb is None:
        return True
    ad = member.advertisement
    if not ad or not ad.gpu or ad.gpu.vram_total_gb is None or ad.gpu.vram_used_gb is None:
        return True
    available = ad.gpu.vram_total_gb - ad.gpu.vram_used_gb
    return available >= (model_size_gb * 1.1)


def latency_rank(
    candidates: list[tuple[MemberInfo, float]],
    *,
    slo_ms: int | None,
    estimated_compute_ms: int,
    coordinator_node_id: str,
) -> tuple[list[tuple[MemberInfo, float]], bool]:
    """Algorithm 7 ordering + SLO fit signal."""
    if not candidates:
        return [], False

    def total_latency(item: tuple[MemberInfo, float]) -> float:
        m, _score = item
        rtt = 0.0
        if m.advertisement:
            rtt = m.advertisement.rtt_ms.get(coordinator_node_id, 0.0)
        return rtt + estimated_compute_ms

    ordered = sorted(candidates, key=total_latency)
    if slo_ms is None:
        return ordered, True
    for item in ordered:
        if total_latency(item) <= (slo_ms * 0.8):
            return ordered, True
    return ordered, False
