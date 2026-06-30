"""Spawn and manage daios-node subprocesses."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from daios_launcher import paths
from daios_launcher.platform_utils import (
    kill_port_listeners,
    popen_kwargs,
    resolve_venv_binary,
    spawn_env,
    terminate_process,
    venv_bin_dir,
)

logger = logging.getLogger(__name__)


class LauncherState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


def _sanitize_log_text(text: str) -> str:
    return "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)


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

        kill_port_listeners(self.api_port)

        self.state = LauncherState.STARTING
        self.last_error = None
        log_dir = project_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"launcher-{self.node_id}.log"

        # Frozen (PyInstaller) production build has no venv: re-invoke this exe with
        # the hidden --run-node subcommand, which dispatches to the node daemon.
        if paths.is_frozen():
            node_cmd = [sys.executable, "--run-node", "-c", str(self.config_path)]
        else:
            daios_node = resolve_venv_binary(project_root, "daios-node")
            if not Path(daios_node).is_file():
                import shutil

                daios_node = shutil.which("daios-node", path=str(venv_bin)) or daios_node
            node_cmd = [daios_node, "-c", str(self.config_path)]

        env = {
            **spawn_env(venv_bin),
            "DAIOS_LOG_DIR": str(log_dir),
        }

        try:
            self._log_handle = open(self._log_path, "wb")
            self.process = subprocess.Popen(
                node_cmd,
                cwd=str(project_root),
                env=env,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                **popen_kwargs(),
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
        terminate_process(self.process, timeout=timeout)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                self.process.kill()
            except OSError:
                pass
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
        kill_port_listeners(api_port)
        if rpc_port and rpc_port != api_port:
            kill_port_listeners(rpc_port)
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


def default_venv_bin(project_root: Path) -> Path:
    return venv_bin_dir(project_root)
