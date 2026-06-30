"""Subprocess management for llama.cpp inference backends."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from daios_protocol.config import NodeConfig
from daios_protocol.health import InferenceStatus, ProcessState

logger = logging.getLogger(__name__)


@dataclass
class ManagedProcess:
    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    log_path: Path | None = None
    process: subprocess.Popen[bytes] | None = None
    state: ProcessState = ProcessState.STOPPED
    last_error: str | None = None
    _log_handle: object | None = None

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        self.state = ProcessState.STARTING
        self.last_error = None
        # Redirect child output to a log file. Streaming subprocess output to a
        # PIPE that nothing drains will deadlock long-running servers (e.g.
        # llama-server) once the OS pipe buffer fills during model loading.
        try:
            if self.log_path is not None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self._log_handle = open(self.log_path, "wb")
                stdout = self._log_handle
            else:
                stdout = subprocess.DEVNULL

            logger.info("Starting %s: %s", self.name, " ".join(self.command))
            self.process = subprocess.Popen(
                self.command,
                env={**os.environ, **self.env},
                stdout=stdout,
                stderr=subprocess.STDOUT,
            )
            time.sleep(0.5)
            if self.process.poll() is not None:
                self.state = ProcessState.FAILED
                self.last_error = self._read_output() or f"{self.name} exited immediately"
                logger.error("%s failed: %s", self.name, self.last_error)
            else:
                self.state = ProcessState.RUNNING
        except OSError as exc:
            self.state = ProcessState.FAILED
            self.last_error = str(exc)
            logger.error("Failed to start %s: %s", self.name, exc)

    def stop(self, timeout: float = 10.0) -> None:
        if not self.process or self.process.poll() is not None:
            self.state = ProcessState.STOPPED
            self.process = None
            self._close_log()
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.state = ProcessState.STOPPED
        self.process = None
        self._close_log()

    def refresh_state(self) -> ProcessState:
        if not self.process:
            self.state = ProcessState.STOPPED
            return self.state
        if self.process.poll() is None:
            self.state = ProcessState.RUNNING
        else:
            if self.state != ProcessState.FAILED:
                self.last_error = self._read_output() or f"{self.name} exited unexpectedly"
            self.state = ProcessState.FAILED
        return self.state

    def _read_output(self) -> str:
        if self.log_path is None or not self.log_path.exists():
            return ""
        try:
            data = self.log_path.read_bytes()
            return data[-4000:].decode("utf-8", errors="replace")
        except OSError:
            return ""

    def _close_log(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None


def _resolve_binary(configured: str, fallbacks: list[str]) -> str:
    candidates = [configured]
    if sys.platform == "win32" and not configured.lower().endswith(".exe"):
        candidates.append(f"{configured}.exe")
    for path in candidates:
        if Path(path).is_file():
            return path
    found = shutil.which(configured)
    if found:
        return found
    for name in fallbacks:
        for variant in (name, f"{name}.exe" if sys.platform == "win32" else name):
            found = shutil.which(variant)
            if found:
                return found
    return configured


class _MockRpcListener:
    """Minimal TCP listener so peer health checks succeed in mock mode."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.Server | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.2)

    def stop(self) -> None:
        if self._loop and self._server:
            self._loop.call_soon_threadsafe(self._server.close)
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        async def _close(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.close()
            await writer.wait_closed()

        self._server = await asyncio.start_server(_close, self._host, self._port)
        async with self._server:
            await self._server.serve_forever()


class InferenceManager:
    """Manages llama-server and ggml-rpc-server subprocesses."""

    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.rpc_server: ManagedProcess | None = None
        self.llama_server: ManagedProcess | None = None
        self._mock_rpc: _MockRpcListener | None = None
        self._started_at: float | None = None
        self._log_dir = Path(
            os.environ.get("DAIOS_LOG_DIR", Path(tempfile.gettempdir()) / "daios-logs")
        )
        self._peer_hosts: list[str] | None = None

    def _log_path(self, name: str) -> Path:
        return self._log_dir / f"{self.config.node_id}-{name}.log"

    def set_peer_hosts(self, hosts: list[str]) -> None:
        """Update RPC peer hosts (Generation 2 discovery). Restarts llama-server if running."""
        if hosts == self._peer_hosts:
            return
        self._peer_hosts = hosts
        if self.config.runs_coordinator and self.config.inference.backend != "mock":
            if self.llama_server and self.llama_server.state == ProcessState.RUNNING:
                self.llama_server.stop()
                self._start_llama_server()

    def start(self) -> None:
        if self.config.inference.backend == "mock":
            if self.config.runs_rpc_server:
                self._mock_rpc = _MockRpcListener(
                    self.config.network.bind_host,
                    self.config.network.rpc_port,
                )
                self._mock_rpc.start()
            self._started_at = time.monotonic()
            return

        if self.config.runs_rpc_server:
            self._start_rpc_server()
        if self.config.runs_coordinator:
            self._start_llama_server()
        self._started_at = time.monotonic()

    def stop(self) -> None:
        if self.llama_server:
            self.llama_server.stop()
        if self.rpc_server:
            self.rpc_server.stop()
        if self._mock_rpc:
            self._mock_rpc.stop()
            self._mock_rpc = None
        self._started_at = None

    def status(self) -> InferenceStatus:
        llama_state = ProcessState.STOPPED
        rpc_state = ProcessState.STOPPED

        if self.config.inference.backend == "mock":
            llama_state = ProcessState.RUNNING if self.config.runs_coordinator else ProcessState.STOPPED
            rpc_state = ProcessState.RUNNING if self.config.runs_rpc_server else ProcessState.STOPPED
        else:
            if self.llama_server:
                llama_state = self.llama_server.refresh_state()
            if self.rpc_server:
                rpc_state = self.rpc_server.refresh_state()

        openai_url = None
        if self.config.runs_coordinator:
            port = self.config.inference.llama_server_port
            openai_url = f"http://127.0.0.1:{port}/v1"

        return InferenceStatus(
            backend=self.config.inference.backend,
            llama_server=llama_state,
            rpc_server=rpc_state,
            model_path=self.config.inference.model_path,
            openai_base_url=openai_url,
        )

    def uptime_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.monotonic() - self._started_at

    def _start_rpc_server(self) -> None:
        inf = self.config.inference
        binary = _resolve_binary(inf.rpc_server_bin, ["ggml-rpc-server", "rpc-server"])
        cmd = [
            binary,
            "--host",
            self.config.network.bind_host,
            "-p",
            str(self.config.network.rpc_port),
        ]
        if inf.rpc_cache:
            cmd.append("-c")
        if inf.threads:
            cmd.extend(["-t", str(inf.threads)])
        cmd.extend(inf.extra_args)
        self.rpc_server = ManagedProcess(
            name="rpc-server", command=cmd, log_path=self._log_path("rpc-server")
        )
        self.rpc_server.start()

    def _start_llama_server(self) -> None:
        inf = self.config.inference
        if not inf.model_path and inf.backend == "llama.cpp":
            raise ValueError("inference.model_path is required for llama.cpp coordinator")

        binary = _resolve_binary(inf.llama_server_bin, ["llama-server"])
        cmd = [
            binary,
            "--host",
            "127.0.0.1",
            "--port",
            str(inf.llama_server_port),
            "-ngl",
            str(inf.n_gpu_layers),
        ]
        if inf.context_size > 0:
            cmd.extend(["-c", str(inf.context_size)])
        if inf.model_path:
            cmd.extend(["-m", inf.model_path])
        if inf.threads:
            cmd.extend(["-t", str(inf.threads), "-tb", str(inf.threads)])

        # Single slot avoids parallel requests competing for CPU/RPC bandwidth.
        cmd.extend(["-np", "1", "--cont-batching", "--mlock"])

        rpc_endpoints = self.config.rpc_endpoints(self._peer_hosts)
        if rpc_endpoints:
            cmd.extend(["--rpc", ",".join(rpc_endpoints)])
        if inf.tensor_split:
            cmd.extend(["--tensor-split", inf.tensor_split])
        if inf.extra_args:
            cmd.extend(inf.extra_args)

        self.llama_server = ManagedProcess(
            name="llama-server", command=cmd, log_path=self._log_path("llama-server")
        )
        self.llama_server.start()
