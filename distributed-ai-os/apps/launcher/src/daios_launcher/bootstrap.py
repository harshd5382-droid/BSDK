"""Windows worker bootstrapper — clone repo, install deps, launch launcher."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from daios_launcher.autostart_windows import install_task, is_windows, uninstall_task
from daios_launcher.settings import LauncherSettings, get_or_create_token
from daios_launcher.update import get_version, pull_latest, reinstall_deps

logger = logging.getLogger(__name__)

DEFAULT_REPO = os.environ.get(
    "DAIOS_REPO_URL",
    "https://github.com/ciright/BSDK.git",
)
DEFAULT_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BSDK"
DEFAULT_INSTALL = DEFAULT_ROOT / "distributed-ai-os"
DEFAULT_BRANCH = os.environ.get("DAIOS_BRANCH", "main")


def _run(cmd: list[str], cwd: Path | None = None, timeout: float = 600.0) -> tuple[int, str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


def _find_python() -> str | None:
    for name in ("python", "python3", "py"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _find_git() -> str | None:
    return shutil.which("git")


def ensure_prerequisites() -> None:
    if not _find_git():
        raise RuntimeError(
            "git is required. Install with: winget install Git.Git"
        )
    if not _find_python():
        raise RuntimeError(
            "Python 3.11+ is required. Install with: winget install Python.Python.3.12"
        )


def ensure_checkout(install_dir: Path, repo_url: str, branch: str) -> None:
    repo_root = install_dir.parent
    repo_root.mkdir(parents=True, exist_ok=True)
    if not (repo_root / ".git").is_dir():
        code, out = _run(
            ["git", "clone", "--depth", "1", "-b", branch, repo_url, str(repo_root)]
        )
        if code != 0:
            code, out = _run(["git", "clone", "--depth", "1", repo_url, str(repo_root)])
        if code != 0:
            raise RuntimeError(f"git clone failed: {out}")
    else:
        pull = pull_latest(repo_root, branch=branch)
        if not pull.ok:
            logger.warning("git pull failed: %s", "; ".join(pull.messages))
    if not install_dir.is_dir():
        raise RuntimeError(
            f"Expected project at {install_dir} — ensure the repo contains distributed-ai-os/"
        )


def ensure_venv(install_dir: Path) -> Path:
    python = _find_python()
    if not python:
        raise RuntimeError("Python not found")
    venv_dir = install_dir / ".venv"
    venv_python = (
        venv_dir / "Scripts" / "python.exe"
        if is_windows()
        else venv_dir / "bin" / "python"
    )
    if not venv_python.is_file():
        code, out = _run([python, "-m", "venv", str(venv_dir)], cwd=install_dir)
        if code != 0:
            raise RuntimeError(f"venv creation failed: {out}")
    reinstall = reinstall_deps(install_dir)
    if not reinstall.ok:
        raise RuntimeError("; ".join(reinstall.messages))
    return venv_python


def launch_worker(
    install_dir: Path,
    *,
    token: str | None = None,
    install_autostart: bool = True,
    exe_path: Path | None = None,
) -> None:
    settings = LauncherSettings.load()
    settings.install_dir = str(install_dir)
    settings.role = "worker"
    settings.autostart_node = True
    settings.cluster_token = token or settings.ensure_token()
    settings.save()

    if install_autostart and is_windows() and exe_path:
        ok, msg = install_task(exe_path)
        logger.info("Autostart task: %s (%s)", ok, msg)

    venv_python = ensure_venv(install_dir)
    version = get_version(install_dir)
    logger.info(
        "Starting DAIOS worker (commit=%s branch=%s)",
        version.commit,
        version.branch,
    )

    os.chdir(install_dir)
    env = {
        **os.environ,
        "DAIOS_ROOT": str(install_dir),
    }
    args = [
        str(venv_python),
        "-m",
        "daios_launcher.cli",
        "--root",
        str(install_dir),
        "--role",
        "worker",
        "--host",
        "0.0.0.0",
        "--token",
        settings.cluster_token,
        "--autostart",
        "--no-window",
    ]
    os.execve(str(venv_python), args, env)


def main() -> None:
    parser = argparse.ArgumentParser(description="DAIOS Windows worker bootstrapper")
    parser.add_argument("--install-dir", type=Path, default=DEFAULT_INSTALL)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--token", default=None, help="Cluster control token")
    parser.add_argument("--no-autostart-task", action="store_true")
    parser.add_argument("--uninstall", action="store_true", help="Remove Task Scheduler entry")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if args.uninstall:
        ok, msg = uninstall_task()
        print(msg)
        sys.exit(0 if ok else 1)

    ensure_prerequisites()
    ensure_checkout(args.install_dir, args.repo, args.branch)
    exe_path = Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__).resolve()
    launch_worker(
        args.install_dir,
        token=args.token,
        install_autostart=not args.no_autostart_task,
        exe_path=exe_path,
    )


if __name__ == "__main__":
    main()
