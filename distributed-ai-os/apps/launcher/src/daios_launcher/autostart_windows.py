"""Windows Task Scheduler integration for auto-start."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

TASK_NAME = "DAIOS Worker"


def is_windows() -> bool:
    return sys.platform == "win32"


def install_task(exe_path: Path) -> tuple[bool, str]:
    if not is_windows():
        return False, "Task Scheduler is Windows-only"
    cmd = [
        "schtasks",
        "/Create",
        "/SC",
        "ONLOGON",
        "/TN",
        TASK_NAME,
        "/TR",
        f'"{exe_path}" --no-window',
        "/RL",
        "LIMITED",
        "/F",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "schtasks failed").strip()
    return True, "Task installed"


def uninstall_task() -> tuple[bool, str]:
    if not is_windows():
        return False, "Task Scheduler is Windows-only"
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 and "ERROR: The system cannot find" not in (result.stderr or ""):
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
