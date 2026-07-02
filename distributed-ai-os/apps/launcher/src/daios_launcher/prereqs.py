"""Developer (Git-based) install prerequisites: Git + Python 3.11+.

Used only by the optional ``--dev`` install path. Validates *versions*, not just
presence, can offer to install missing tools via ``winget`` (never silently), and
refreshes executable discovery afterward by re-reading the Windows PATH.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

MIN_PYTHON = (3, 11)

# winget package IDs.
WINGET_GIT = "Git.Git"
WINGET_PYTHON = "Python.Python.3.12"


@dataclass
class ToolInfo:
    name: str
    path: str | None = None
    version: tuple[int, ...] | None = None
    ok: bool = False
    reason: str | None = None
    winget_id: str | None = None

    @property
    def version_str(self) -> str:
        return ".".join(str(p) for p in self.version) if self.version else "unknown"


def find_tool(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _run(cmd: list[str], timeout: float = 30.0) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _parse_version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    return tuple(int(g) for g in match.groups() if g is not None)


def check_python() -> ToolInfo:
    info = ToolInfo(name="Python", winget_id=WINGET_PYTHON)
    path = find_tool("python", "python3", "py")
    if not path:
        info.reason = "Python not found"
        return info
    info.path = path
    code, out = _run([path, "--version"])
    info.version = _parse_version(out)
    if code != 0 or not info.version:
        info.reason = f"Could not read Python version ({out})"
        return info
    if info.version < MIN_PYTHON:
        info.reason = (
            f"Python {info.version_str} is too old "
            f"(need >= {'.'.join(map(str, MIN_PYTHON))})"
        )
        return info
    info.ok = True
    return info


def check_git() -> ToolInfo:
    info = ToolInfo(name="Git", winget_id=WINGET_GIT)
    path = find_tool("git")
    if not path:
        info.reason = "Git not found"
        return info
    info.path = path
    code, out = _run([path, "--version"])
    info.version = _parse_version(out)
    if code != 0:
        info.reason = f"git --version failed ({out})"
        return info
    info.ok = True
    return info


def winget_available() -> bool:
    return sys.platform == "win32" and shutil.which("winget") is not None


def winget_install(
    package_id: str, *, on_message: Callable[[str], None] = logger.info
) -> bool:
    """Install a package via winget. Always announces what it is doing."""
    if not winget_available():
        on_message(
            "winget is unavailable. Install it from the Microsoft Store "
            "('App Installer'), or install the dependency manually."
        )
        return False
    on_message(f"Installing {package_id} via winget (this may take a few minutes)...")
    code, out = _run(
        [
            "winget",
            "install",
            "--id",
            package_id,
            "-e",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--silent",
        ],
        timeout=900.0,
    )
    if code != 0:
        on_message(f"winget failed to install {package_id}: {out}")
        return False
    on_message(f"Installed {package_id}.")
    return True


def refresh_path() -> None:
    """Re-read PATH from the Windows registry so freshly-installed tools resolve.

    winget installs to locations not on the current process's inherited PATH; this
    rebuilds ``os.environ['PATH']`` from the machine + user environment.
    """
    if sys.platform != "win32":
        return
    try:
        import winreg
    except ImportError:
        return
    parts: list[str] = []
    sources = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ]
    for root, sub in sources:
        try:
            with winreg.OpenKey(root, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                if value:
                    parts.append(os.path.expandvars(value))
        except OSError:
            continue
    if parts:
        os.environ["PATH"] = os.pathsep.join(parts + [os.environ.get("PATH", "")])


def ensure_dev_prerequisites(
    *,
    auto_install: bool = False,
    installer: Callable[..., bool] = winget_install,
    on_message: Callable[[str], None] = logger.info,
) -> tuple[bool, list[ToolInfo]]:
    """Check Git + Python; optionally install missing ones via winget.

    Returns ``(all_ok, [tool_infos])``. Never installs silently: when
    ``auto_install`` is False, missing tools are reported with guidance only.
    """
    tools = [check_git(), check_python()]
    missing = [t for t in tools if not t.ok]
    if not missing:
        return True, tools

    for tool in missing:
        on_message(f"{tool.name}: {tool.reason}")

    if not auto_install:
        on_message(
            "Install the tools above, or re-run with consent to use winget. "
            "winget command: "
            + "; ".join(f"winget install --id {t.winget_id} -e" for t in missing)
        )
        return False, tools

    if not winget_available():
        on_message(
            "Cannot auto-install: winget is unavailable. Install 'App Installer' "
            "from the Microsoft Store, then re-run."
        )
        return False, tools

    for tool in missing:
        if tool.winget_id:
            installer(tool.winget_id, on_message=on_message)

    refresh_path()  # refresh executable discovery before re-validating
    rechecked = [check_git(), check_python()]
    return all(t.ok for t in rechecked), rechecked
