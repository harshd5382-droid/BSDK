"""Local system information for the dashboard."""

from __future__ import annotations

import socket
from pathlib import Path

import psutil
from pydantic import BaseModel


class SystemInfo(BaseModel):
    hostname: str
    lan_ip: str
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


def list_models(models_dir: Path) -> list[str]:
    if not models_dir.is_dir():
        return []
    return sorted(str(p.relative_to(models_dir)) for p in models_dir.glob("*.gguf"))


def gather_system_info(project_root: Path) -> SystemInfo:
    mem = psutil.virtual_memory()
    models_dir = project_root / "models"
    return SystemInfo(
        hostname=socket.gethostname(),
        lan_ip=get_lan_ip(),
        cpu_count=psutil.cpu_count(logical=True) or 1,
        ram_total_gb=round(mem.total / (1024**3), 1),
        ram_available_gb=round(mem.available / (1024**3), 1),
        models=list_models(models_dir),
    )
