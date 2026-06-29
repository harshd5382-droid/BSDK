"""Spawn and manage daios-node subprocesses."""

from __future__ import annotations

import logging
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class LauncherState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


def _sanitize_log_text(text: str) -> str:
    return "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)


def _kill_port_listeners(port: int) -> None:
    """Terminate processes still bound to a TCP port (e.g. orphaned daios-node)."""
    pids: set[int] = set()
    try:
        result = subprocess.run(
            ["ss", "-ltnp", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for match in re.finditer(r"pid=(\d+)", result.stdout):
            pids.add(int(match.group(1)))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        try:
            subprocess.run(
                ["fuser", "-k", f"{port}/tcp"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            time.sleep(0.5)
            return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if pids:
        time.sleep(0.5)


@dataclass
class NodeProcess:
    config_path: Path
    role: str
    node_id: str
    api_port: int = 8000
    process: subprocess.Popen[bytes] | None = None
    state: LauncherState = LauncherState.STOPPED
    last_error: str | None = None
    started_at: float | None = None
    _log_path: Path | None = None
    _log_handle: object | None = None

    def start(self, project_root: Path, venv_bin: Path) -> None:
        if self.process and self.process.poll() is None:
            return

        _kill_port_listeners(self.api_port)

        self.state = LauncherState.STARTING
        self.last_error = None
        log_dir = project_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"launcher-{self.node_id}.log"

        daios_node = shutil.which("daios-node", path=str(venv_bin))
        if not daios_node:
            daios_node = str(venv_bin / "daios-node")

        env = {
            **os.environ,
            "PATH": f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "LD_LIBRARY_PATH": str(venv_bin),
            "DAIOS_LOG_DIR": str(log_dir),
        }

        try:
            self._log_handle = open(self._log_path, "wb")
            self.process = subprocess.Popen(
                [daios_node, "-c", str(self.config_path)],
                cwd=str(project_root),
                env=env,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            time.sleep(1.0)
            if self.process.poll() is not None:
                self.state = LauncherState.FAILED
                self.last_error = self.read_log_tail() or "daios-node exited immediately"
                logger.error("Node failed to start: %s", self.last_error)
            else:
                self.state = LauncherState.RUNNING
                self.started_at = time.monotonic()
        except OSError as exc:
            self.state = LauncherState.FAILED
            self.last_error = str(exc)
            logger.error("Failed to spawn daios-node: %s", exc)

    def stop(self, timeout: float = 10.0) -> None:
        if not self.process or self.process.poll() is not None:
            self._cleanup()
            self.state = LauncherState.STOPPED
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.process.wait(timeout=timeout)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=5)
        self._cleanup()
        self.state = LauncherState.STOPPED

    def refresh(self) -> LauncherState:
        if not self.process:
            self.state = LauncherState.STOPPED
            return self.state
        if self.process.poll() is None:
            self.state = LauncherState.RUNNING
        else:
            if self.state != LauncherState.FAILED:
                self.last_error = self.read_log_tail() or "daios-node exited unexpectedly"
            self.state = LauncherState.FAILED
        return self.state

    def uptime_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        return time.monotonic() - self.started_at

    def read_log_tail(self, max_bytes: int = 8000) -> str:
        if self._log_path and self._log_path.exists():
            data = self._log_path.read_bytes()
            return _sanitize_log_text(data[-max_bytes:].decode("utf-8", errors="replace"))
        return ""

    def _cleanup(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None
        self.process = None
        self.started_at = None


@dataclass
class ProcessManager:
    project_root: Path
    venv_bin: Path
    runtime_dir: Path
    node: NodeProcess | None = None

    def start_node(
        self,
        config_path: Path,
        role: str,
        node_id: str,
        api_port: int,
        rpc_port: int | None = None,
    ) -> NodeProcess:
        if self.node:
            self.node.stop()
        _kill_port_listeners(api_port)
        if rpc_port and rpc_port != api_port:
            _kill_port_listeners(rpc_port)
        self.node = NodeProcess(
            config_path=config_path,
            role=role,
            node_id=node_id,
            api_port=api_port,
        )
        self.node.start(self.project_root, self.venv_bin)
        return self.node

    def stop_node(self) -> None:
        if self.node:
            self.node.stop()
            self.node = None
