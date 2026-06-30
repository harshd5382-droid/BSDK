"""Per-user installation layout for the self-contained Windows worker.

Everything lives under ``%LOCALAPPDATA%\\BSDK`` (override with ``DAIOS_HOME``) so a
standard user can install without administrator rights. These helpers are the
single source of truth for where the runtime binaries, logs, runtime configs, and
models live, used by both the bootstrapper and the frozen node/launcher.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def install_root() -> Path:
    """Root of the per-user install (``%LOCALAPPDATA%\\BSDK``).

    ``DAIOS_HOME`` overrides it (used by tests and advanced users). On non-Windows
    hosts (dev/test) fall back to ``~/.local/share/BSDK`` so the module imports and
    is testable everywhere.
    """
    override = os.environ.get("DAIOS_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "BSDK"
    return Path.home() / ".local" / "share" / "BSDK"


def bin_dir() -> Path:
    """Where ``ggml-rpc-server.exe`` and its GGML DLLs are materialized."""
    return install_root() / "bin"


def logs_dir() -> Path:
    return install_root() / "logs"


def runtime_dir() -> Path:
    """Generated node YAML configs."""
    return install_root() / "runtime"


def models_dir() -> Path:
    return install_root() / "models"


def staging_dir() -> Path:
    """Scratch area for atomic downloads/updates (same volume as the target)."""
    return install_root() / ".staging"


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle (production exe)."""
    return bool(getattr(sys, "frozen", False))


def bundled_dir() -> Path | None:
    """PyInstaller extraction root (``sys._MEIPASS``) when frozen, else None."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def ensure_layout() -> None:
    """Create the install directories (idempotent)."""
    for d in (install_root(), bin_dir(), logs_dir(), runtime_dir(), models_dir()):
        d.mkdir(parents=True, exist_ok=True)
