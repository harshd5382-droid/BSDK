"""Git-based self-update for the launcher bootstrapper."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VersionInfo:
    commit: str | None = None
    branch: str | None = None
    dirty: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "commit": self.commit,
            "branch": self.branch,
            "dirty": self.dirty,
            "error": self.error,
        }


@dataclass
class UpdateResult:
    ok: bool
    messages: list[str] = field(default_factory=list)
    version: VersionInfo | None = None


def _run(cmd: list[str], cwd: Path, timeout: float = 300.0) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode, output.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def get_version(install_dir: Path) -> VersionInfo:
    info = VersionInfo()
    if not (install_dir / ".git").is_dir():
        info.error = "not a git repository"
        return info
    code, out = _run(["git", "rev-parse", "HEAD"], install_dir, timeout=30)
    if code == 0:
        info.commit = out.splitlines()[-1][:12]
    code, out = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], install_dir, timeout=30)
    if code == 0:
        info.branch = out.splitlines()[-1]
    code, _ = _run(["git", "diff", "--quiet"], install_dir, timeout=30)
    info.dirty = code != 0
    return info


def pull_latest(install_dir: Path, branch: str | None = None) -> UpdateResult:
    messages: list[str] = []
    if not (install_dir / ".git").is_dir():
        return UpdateResult(ok=False, messages=["Install directory is not a git repository"])

    branch = branch or get_version(install_dir).branch or "main"
    messages.append(f"Fetching origin/{branch}…")
    code, out = _run(["git", "fetch", "origin", branch], install_dir)
    messages.append(out or f"fetch exit {code}")
    if code != 0:
        return UpdateResult(ok=False, messages=messages)

    code, out = _run(["git", "reset", "--hard", f"origin/{branch}"], install_dir)
    messages.append(out or f"reset exit {code}")
    if code != 0:
        return UpdateResult(ok=False, messages=messages)

    return UpdateResult(ok=True, messages=messages, version=get_version(install_dir))


def reinstall_deps(install_dir: Path) -> UpdateResult:
    """Reinstall Python packages after a git pull."""
    messages: list[str] = []
    venv_python = _venv_python(install_dir)
    if not venv_python:
        return UpdateResult(ok=False, messages=["Virtual environment not found"])

    packages = [
        install_dir / "packages" / "protocol",
        install_dir / "apps" / "node",
        install_dir / "apps" / "launcher",
    ]
    for pkg in packages:
        if not pkg.is_dir():
            continue
        code, out = _run(
            [str(venv_python), "-m", "pip", "install", "-e", str(pkg)],
            install_dir,
        )
        messages.append(f"pip install -e {pkg.name}: {'ok' if code == 0 else out}")
        if code != 0:
            return UpdateResult(ok=False, messages=messages)

    code, out = _run(
        [str(venv_python), "-m", "pip", "install", "zeroconf", "huggingface_hub"],
        install_dir,
    )
    messages.append(f"optional deps: {'ok' if code == 0 else out}")
    return UpdateResult(ok=True, messages=messages)


def _venv_python(install_dir: Path) -> Path | None:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        candidate = install_dir / rel
        if candidate.is_file():
            return candidate
    return None


def reexec_launcher(install_dir: Path, extra_args: list[str]) -> None:
    """Replace current process with a fresh launcher invocation."""
    venv_python = _venv_python(install_dir)
    if not venv_python:
        logger.error("Cannot re-exec: venv python missing")
        return
    env = {**os.environ, "DAIOS_ROOT": str(install_dir)}
    os.chdir(install_dir)
    os.execve(
        str(venv_python),
        [str(venv_python), "-m", "daios_launcher.cli", *extra_args],
        env,
    )
