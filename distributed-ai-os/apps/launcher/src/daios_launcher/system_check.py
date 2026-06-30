"""Pre-flight system detection and validation for the Windows worker installer.

Reports the Windows version, CPU architecture, RAM/disk, network connectivity,
required-port availability, and whether the worker is already installed/running.
A Windows ``.exe`` cannot run elsewhere, so non-Windows or non-x64 systems are
flagged ``supported = False`` with an actionable reason.
"""

from __future__ import annotations

import platform
import shutil
import socket
import sys
from pathlib import Path

import psutil
from pydantic import BaseModel

from daios_launcher import paths

# Worker port allocation (kept in sync with config_gen defaults).
API_PORT = 8001
RPC_PORT = 50052
LAUNCHER_PORT = 8090
REQUIRED_PORTS = (API_PORT, RPC_PORT, LAUNCHER_PORT)

# Minimums for a usable real (non-mock) worker.
MIN_RAM_GB = 2.0
MIN_DISK_GB = 2.0

_X64_MACHINES = {"AMD64", "X86_64", "X64"}


class PortStatus(BaseModel):
    port: int
    in_use: bool


class SystemReport(BaseModel):
    supported: bool
    unsupported_reason: str | None = None
    os_name: str
    os_version: str
    os_release: str
    architecture: str
    is_windows: bool
    is_x64: bool
    cpu_count: int
    ram_total_gb: float
    ram_available_gb: float
    disk_free_gb: float
    network_ok: bool
    ports: list[PortStatus]
    already_installed: bool
    already_running: bool

    def blocking_errors(self) -> list[str]:
        """Hard failures that must stop a real install (empty == proceed)."""
        errors: list[str] = []
        if not self.supported:
            errors.append(self.unsupported_reason or "Unsupported system")
        if self.ram_total_gb < MIN_RAM_GB:
            errors.append(
                f"Insufficient RAM: {self.ram_total_gb:.1f} GB (need >= {MIN_RAM_GB:.0f} GB)"
            )
        if self.disk_free_gb < MIN_DISK_GB:
            errors.append(
                f"Insufficient disk space: {self.disk_free_gb:.1f} GB free "
                f"(need >= {MIN_DISK_GB:.0f} GB)"
            )
        return errors


def _detect_unsupported() -> str | None:
    """Return a reason string if this host cannot run the worker, else None."""
    if sys.platform != "win32":
        return (
            f"This installer runs on Windows only (detected {platform.system()}). "
            "A Windows .exe cannot run on Linux or macOS."
        )
    machine = platform.machine().upper()
    if machine not in _X64_MACHINES:
        return (
            f"Unsupported CPU architecture: {platform.machine()}. "
            "Windows 10/11 x64 is required (ARM is not supported yet)."
        )
    # Windows 10 reports release '10', Windows 11 also reports '10' with build >= 22000.
    try:
        build = int(platform.version().split(".")[-1])
    except (ValueError, IndexError):
        build = 0
    release = platform.release()
    if release not in ("10", "11") and build < 10240:
        return (
            f"Unsupported Windows version: {platform.platform()}. "
            "Windows 10 or 11 (x64) is required."
        )
    return None


def port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    """True if ``port`` cannot be bound (already taken)."""
    # No SO_REUSEADDR: on Windows it would let us bind a port another process is
    # already using, producing a false "free" reading.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return False
        except OSError:
            return True


def check_network(host: str = "8.8.8.8", port: int = 53, timeout: float = 3.0) -> bool:
    """True if outbound TCP works (needed to download the RPC binary)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _worker_running() -> bool:
    """Best-effort check that a worker API or launcher is already serving."""
    for port in (API_PORT, LAUNCHER_PORT):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            continue
    return False


def _already_installed() -> bool:
    rpc = paths.bin_dir() / "ggml-rpc-server.exe"
    if rpc.is_file():
        return True
    try:
        from daios_launcher.settings import LauncherSettings

        if LauncherSettings.load().install_dir:
            return True
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            from daios_launcher.autostart_windows import task_installed

            if task_installed():
                return True
        except Exception:
            pass
    return False


def check_system(install_path: Path | None = None, *, probe_network: bool = True) -> SystemReport:
    """Gather a full pre-flight report. Pure detection — no side effects."""
    mem = psutil.virtual_memory()
    target = install_path or paths.install_root()
    # disk_usage needs an existing path; walk up to the first one that exists.
    probe = target
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        disk_free = shutil.disk_usage(str(probe)).free / (1024**3)
    except OSError:
        disk_free = 0.0

    reason = _detect_unsupported()
    return SystemReport(
        supported=reason is None,
        unsupported_reason=reason,
        os_name=platform.system(),
        os_version=platform.version(),
        os_release=platform.release(),
        architecture=platform.machine(),
        is_windows=sys.platform == "win32",
        is_x64=platform.machine().upper() in _X64_MACHINES,
        cpu_count=psutil.cpu_count(logical=True) or 1,
        ram_total_gb=round(mem.total / (1024**3), 1),
        ram_available_gb=round(mem.available / (1024**3), 1),
        disk_free_gb=round(disk_free, 1),
        network_ok=check_network() if probe_network else False,
        ports=[PortStatus(port=p, in_use=port_in_use(p)) for p in REQUIRED_PORTS],
        already_installed=_already_installed(),
        already_running=_worker_running(),
    )


def format_report(report: SystemReport) -> str:
    """Human-readable multi-line summary for the console."""
    ok = "OK"
    lines = [
        "BSDK Worker - system check",
        "==========================",
        f"  OS            : {report.os_name} {report.os_release} ({report.os_version})",
        f"  Architecture  : {report.architecture} "
        f"({'x64 ' + ok if report.is_x64 else 'UNSUPPORTED'})",
        f"  CPU cores     : {report.cpu_count}",
        f"  RAM           : {report.ram_available_gb:.1f} GB free / "
        f"{report.ram_total_gb:.1f} GB total",
        f"  Disk free     : {report.disk_free_gb:.1f} GB",
        f"  Network       : {'reachable ' + ok if report.network_ok else 'NOT reachable'}",
        "  Ports         : "
        + ", ".join(
            f"{p.port} {'IN USE' if p.in_use else 'free'}" for p in report.ports
        ),
        f"  Installed     : {'yes' if report.already_installed else 'no'}",
        f"  Running       : {'yes' if report.already_running else 'no'}",
    ]
    if not report.supported:
        lines.append("")
        lines.append(f"  ERROR: {report.unsupported_reason}")
    return "\n".join(lines)
