"""Windows Task Scheduler integration for auto-start at login.

The scheduled task runs the *installed* executable in service mode
(``"<exe>" --service``). Previously it passed ``--no-window`` to the bootstrapper
entry point, which does not accept that flag — the task errored on every login.
``--service`` is handled by ``bootstrap.main`` and starts the worker launcher with
the browser suppressed.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

TASK_NAME = "DAIOS Worker"
SERVICE_FLAG = "--service"


def is_windows() -> bool:
    return sys.platform == "win32"


def _task_command(exe_path: Path) -> str:
    """The full command the scheduler should run (quoted for spaces in path)."""
    return f'"{exe_path}" {SERVICE_FLAG}'


def current_task_command() -> str | None:
    """Return the configured 'Task To Run' string, or None if no task exists."""
    if not is_windows():
        return None
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    for line in (result.stdout or "").splitlines():
        if line.strip().lower().startswith("task to run:"):
            return line.split(":", 1)[1].strip()
    return None


def install_task(exe_path: Path) -> tuple[bool, str]:
    """Create or update the login task. Idempotent — no duplicate tasks.

    Always uses ``exe_path`` (the installed executable). If a task already exists
    with the identical command it is left untouched.
    """
    if not is_windows():
        return False, "Task Scheduler is Windows-only"

    exe_path = Path(exe_path)
    desired = _task_command(exe_path)
    existing = current_task_command()
    if existing is not None and existing.strip().strip('"') == desired.strip().strip('"'):
        return True, "Task already current"
    if existing is not None and existing.replace('"', "") == desired.replace('"', ""):
        return True, "Task already current"

    # /F replaces an existing task in place, so re-running never duplicates it.
    cmd = [
        "schtasks",
        "/Create",
        "/SC",
        "ONLOGON",
        "/TN",
        TASK_NAME,
        "/TR",
        desired,
        "/RL",
        "LIMITED",
        "/F",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "schtasks failed").strip()
    return True, "Task installed" if existing is None else "Task updated"


def uninstall_task() -> tuple[bool, str]:
    if not is_windows():
        return False, "Task Scheduler is Windows-only"
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 and "cannot find" not in (result.stderr or "").lower():
        return False, (result.stderr or result.stdout or "schtasks failed").strip()
    return True, "Task removed"


def task_installed() -> bool:
    if not is_windows():
        return False
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0
