"""Cross-platform helpers for process and binary management."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import psutil


def venv_bin_dir(project_root: Path) -> Path:
    """Return the venv binary directory (``bin`` on POSIX, ``Scripts`` on Windows)."""
    scripts = project_root / ".venv" / "Scripts"
    if scripts.is_dir():
        return scripts
    return project_root / ".venv" / "bin"


def resolve_venv_binary(project_root: Path, name: str) -> str:
    """Resolve a binary inside the project venv, with ``.exe`` on Windows."""
    bin_dir = venv_bin_dir(project_root)
    candidates = [bin_dir / name]
    if sys.platform == "win32":
        candidates.insert(0, bin_dir / f"{name}.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return str(candidates[0])


def spawn_env(venv_bin: Path) -> dict[str, str]:
    """Build environment for child processes with bundled binaries on PATH."""
    env = {**os.environ}
    bin_str = str(venv_bin)
    env["PATH"] = f"{bin_str}{os.pathsep}{env.get('PATH', '')}"
    if sys.platform != "win32":
        env["LD_LIBRARY_PATH"] = bin_str
    return env


def popen_kwargs() -> dict:
    """Platform-specific kwargs for ``subprocess.Popen``."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess := __import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def kill_port_listeners(port: int) -> None:
    """Terminate processes listening on or bound to a TCP port."""
    pids: set[int] = set()
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port and conn.pid:
                pids.add(conn.pid)
    except (psutil.AccessDenied, psutil.Error):
        return

    for pid in pids:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if pids:
        time.sleep(0.5)


def terminate_process(process, timeout: float = 10.0) -> None:
    """Terminate a subprocess and its children cross-platform."""
    if process is None or process.poll() is not None:
        return
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        parent.terminate()
        gone, alive = psutil.wait_procs([parent, *children], timeout=timeout)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        try:
            process.terminate()
            process.wait(timeout=timeout)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
