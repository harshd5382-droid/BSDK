"""Local system information for the dashboard."""

from __future__ import annotations

import socket
from pathlib import Path

import psutil
from pydantic import BaseModel


class SystemInfo(BaseModel):
    hostname: str
    lan_ip: str
    local_ips: list[str]
    cpu_count: int
    ram_total_gb: float
    ram_available_gb: float
    models: list[str]


def get_lan_ip() -> str:
    """Return the primary LAN IP via UDP socket trick (no packets sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def get_local_addresses() -> set[str]:
    """All addresses that refer to this machine."""
    addresses = {"127.0.0.1", "0.0.0.0", "::1", "localhost"}
    addresses.add(get_lan_ip())
    try:
        hostname = socket.gethostname().lower()
        addresses.add(hostname)
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    for addrs in psutil.net_if_addrs().values():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                addresses.add(addr.address)
    return addresses


def gather_local_ips() -> list[str]:
    """Sorted LAN-relevant addresses for this machine."""
    return sorted(
        ip for ip in get_local_addresses() if ip not in {"0.0.0.0", "localhost", "::1"}
    )


def normalize_host(host: str) -> str:
    text = host.strip().lower()
    if text == "localhost":
        return "127.0.0.1"
    if ":" in text and not text.startswith("["):
        text = text.split(":", 1)[0]
    return text


def is_local_address(host: str, local_ips: set[str] | None = None) -> bool:
    local_ips = local_ips or get_local_addresses()
    normalized = normalize_host(host)
    return normalized in {normalize_host(ip) for ip in local_ips}


def list_models(models_dir: Path) -> list[str]:
    if not models_dir.is_dir():
        return []
    return sorted(str(p.relative_to(models_dir)) for p in models_dir.glob("*.gguf"))


def gather_system_info(project_root: Path) -> SystemInfo:
    mem = psutil.virtual_memory()
    models_dir = project_root / "models"
    lan_ip = get_lan_ip()
    return SystemInfo(
        hostname=socket.gethostname(),
        lan_ip=lan_ip,
        local_ips=gather_local_ips(),
        cpu_count=psutil.cpu_count(logical=True) or 1,
        ram_total_gb=round(mem.total / (1024**3), 1),
        ram_available_gb=round(mem.available / (1024**3), 1),
        models=list_models(models_dir),
    )
