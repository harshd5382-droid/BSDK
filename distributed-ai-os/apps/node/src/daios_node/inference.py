"""Subprocess management for llama.cpp inference backends."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from daios_protocol.config import NodeConfig
from daios_protocol.health import (
    DeviceAllocation,
    DistributionDiagnostics,
    InferenceStatus,
    NodeCapabilities,
    ProcessState,
)

from daios_node.allocation import (
    compute_allocation,
    parse_device_listing,
    probe_llama_devices,
    redact_command,
)

logger = logging.getLogger(__name__)

# Debounce for topology-driven llama-server restarts when no distribution
# config is present (legacy configs get safe restarts too).
_DEFAULT_RESTART_DEBOUNCE = 10.0


def _tcp_ready(host: str, port: int, timeout: float = 1.0) -> bool:
    """One connect/close probe. Only used against endpoints that are NOT in
    the running llama-server's --rpc list, so the single-threaded
    ggml-rpc-server on the other end is never busy when we poke it."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


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

            logger.info("Starting %s: %s", self.name, " ".join(redact_command(self.command)))
            # CREATE_NO_WINDOW: output goes to the log file; without it a console
            # child (llama-server / ggml-rpc-server) of a windowed parent pops up
            # its own console window on Windows.
            self.process = subprocess.Popen(
                self.command,
                env={**os.environ, **self.env},
                stdout=stdout,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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
        self._excluded_hosts: set[str] = set()
        self._restart_timestamps: dict[str, deque[float]] = defaultdict(deque)
        self._restart_backoff: dict[str, float] = {}
        self._restart_window_seconds = 600.0
        # --- distribution / topology state ---
        self._lifecycle_lock = threading.Lock()
        self._worker_caps: dict[str, NodeCapabilities] = {}  # by host
        self._worker_rtt: dict[str, float] = {}  # by host
        self._topology_changed_at: float = 0.0
        self._launched_endpoints: list[str] | None = None
        self._llama_start_deferred: bool = False
        self._defer_deadline: float = 0.0
        self._reload_requested: bool = False
        self._restart_state: str = "idle"
        self._restart_error: str | None = None
        self._last_devices: list[DeviceAllocation] = []
        self._last_tensor_split: str | None = None
        self._excluded_endpoints: dict[str, str] = {}
        self._fallback_reason: str | None = None
        self._effective_command: list[str] | None = None

    def _log_path(self, name: str) -> Path:
        return self._log_dir / f"{self.config.node_id}-{name}.log"

    def set_peer_hosts(self, hosts: list[str]) -> None:
        """Update RPC peer hosts (Generation 2 discovery).

        Takes effect in ``rpc_endpoints_effective()`` immediately; a running
        llama-server is NOT restarted inline — the topology is marked stale
        and ``maybe_apply_topology`` restarts it safely (debounced, and only
        once active requests drain).
        """
        if hosts == self._peer_hosts:
            return
        self._peer_hosts = hosts
        self._topology_changed_at = time.monotonic()

    def set_excluded_hosts(self, hosts: set[str]) -> None:
        """Exclude worker hosts from the RPC pool (temporary disconnect).

        The workers stay up and remain cluster members; their memory just isn't
        pooled. Applies to both static (Gen 1) and discovered (Gen 2) peers.
        Like ``set_peer_hosts``, the restart is deferred and safe.
        """
        if hosts == self._excluded_hosts:
            return
        self._excluded_hosts = set(hosts)
        self._topology_changed_at = time.monotonic()

    def set_worker_capabilities(self, caps: dict[str, NodeCapabilities]) -> None:
        """Advertised capabilities of worker nodes, keyed by host."""
        self._worker_caps = dict(caps)

    def set_worker_rtt(self, rtt_ms: dict[str, float]) -> None:
        """Measured heartbeat round-trip time per worker host (ms)."""
        self._worker_rtt = dict(rtt_ms)

    def rpc_endpoints_effective(self) -> list[str]:
        """The RPC endpoints llama-server would be started with right now."""
        endpoints = self.config.rpc_endpoints(self._peer_hosts)
        return [ep for ep in endpoints if ep.rsplit(":", 1)[0] not in self._excluded_hosts]

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
            dist = self.config.inference.distribution
            if (
                dist is not None
                and self.config.discovery_enabled
                and not self.rpc_endpoints_effective()
            ):
                # Gen 2 + distribution: don't load the model with zero workers
                # only to reload seconds later when discovery finds them. Wait
                # up to wait_for_workers_seconds, then start solo.
                self._llama_start_deferred = True
                self._defer_deadline = time.monotonic() + dist.wait_for_workers_seconds
                self._restart_state = "pending"
                logger.info(
                    "Deferring llama-server start up to %.0fs while discovery finds workers",
                    dist.wait_for_workers_seconds,
                )
            else:
                self._start_llama_server()
        self._started_at = time.monotonic()

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self.llama_server:
                self.llama_server.stop()
            if self.rpc_server:
                self.rpc_server.stop()
            if self._mock_rpc:
                self._mock_rpc.stop()
                self._mock_rpc = None
            self._started_at = None
            self._llama_start_deferred = False
            self._restart_state = "idle"
            self._restart_timestamps.clear()
            self._restart_backoff.clear()

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
            llama_server_pending=self._llama_start_deferred,
        )

    def uptime_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.monotonic() - self._started_at

    def ensure_running(self) -> None:
        """Refresh states and attempt bounded auto-restarts."""
        if self.config.inference.backend == "mock":
            return
        if self.config.inference.auto_restart is False:
            return

        with self._lifecycle_lock:
            if self.rpc_server:
                self._ensure_process_running(
                    self.rpc_server,
                    self._start_rpc_server,
                    should_run=self.config.runs_rpc_server,
                )
            if self.llama_server:
                self._ensure_process_running(
                    self.llama_server,
                    self._start_llama_server,
                    should_run=self.config.runs_coordinator,
                )

    # ------------------------------------------------------------------
    # Topology lifecycle (late worker joins / departures / pause-resume)
    # ------------------------------------------------------------------

    @property
    def topology_stale(self) -> bool:
        """True when the running llama-server's --rpc list no longer matches
        the desired RPC topology (llama.cpp cannot add RPC devices to a
        loaded model — a controlled restart is required)."""
        if self.config.inference.backend == "mock" or not self.config.runs_coordinator:
            return False
        if self._llama_start_deferred:
            return True
        if self.llama_server is None or self.llama_server.state != ProcessState.RUNNING:
            return False
        return sorted(self._launched_endpoints or []) != sorted(self.rpc_endpoints_effective())

    def request_reload(self) -> str:
        """Operator-triggered model reload with the current topology.

        Bypasses the debounce but still waits for active requests to finish;
        applied by ``maybe_apply_topology`` on the next lifecycle tick.
        """
        self._reload_requested = True
        self._restart_state = "pending"
        return self._restart_state

    def _restart_debounce(self) -> float:
        dist = self.config.inference.distribution
        return dist.restart_debounce_seconds if dist else _DEFAULT_RESTART_DEBOUNCE

    def maybe_apply_topology(self, active_requests: int = 0) -> None:
        """Apply pending topology changes with a controlled llama-server restart.

        Called periodically (and never inline from request handlers) so that:
        - unstable discovery events are debounced, not applied one by one;
        - active inference requests and leases drain before the restart;
        - a worker that merely *announced* itself but whose RPC port is not
          reachable yet does not trigger a restart loop.
        """
        if self.config.inference.backend == "mock" or not self.config.runs_coordinator:
            return

        with self._lifecycle_lock:
            now = time.monotonic()

            if self._llama_start_deferred:
                endpoints = self.rpc_endpoints_effective()
                if endpoints and now - self._topology_changed_at >= self._restart_debounce():
                    logger.info("Workers discovered; starting llama-server with --rpc %s", endpoints)
                elif now < self._defer_deadline:
                    return
                else:
                    logger.warning(
                        "No workers became ready within wait_for_workers_seconds; "
                        "starting llama-server with local resources only"
                    )
                self._llama_start_deferred = False
                self._run_controlled_restart()
                return

            force = self._reload_requested
            if not force and not self.topology_stale:
                if self._restart_state == "pending":
                    self._restart_state = "idle"
                return

            if not force:
                if now - self._topology_changed_at < self._restart_debounce():
                    self._restart_state = "pending"
                    return
                # Don't restart for endpoints that were announced but are not
                # actually reachable yet — that would loop through failed loads.
                launched = set(self._launched_endpoints or [])
                effective = set(self.rpc_endpoints_effective())
                added = effective - launched
                removed = launched - effective
                if added and not removed:
                    reachable = [ep for ep in added if self._endpoint_ready(ep)]
                    if not reachable:
                        self._restart_state = "pending"
                        return

            if active_requests > 0:
                self._restart_state = "pending"
                logger.info(
                    "Topology change pending: waiting for %d active request(s) to finish",
                    active_requests,
                )
                return

            self._reload_requested = False
            self._run_controlled_restart()

    def _run_controlled_restart(self) -> None:
        self._restart_state = "running"
        self._restart_error = None
        try:
            if self.llama_server is not None:
                self.llama_server.stop()
            self._start_llama_server()
            state = (
                self.llama_server.refresh_state() if self.llama_server else ProcessState.FAILED
            )
            if state == ProcessState.RUNNING:
                self._restart_state = "success"
                logger.info(
                    "llama-server restarted with RPC endpoints %s", self._launched_endpoints
                )
            else:
                self._restart_state = "failed"
                self._restart_error = (
                    self.llama_server.last_error if self.llama_server else "not started"
                )
                logger.error("llama-server restart failed: %s", self._restart_error)
        except Exception as exc:  # pragma: no cover - defensive
            self._restart_state = "failed"
            self._restart_error = str(exc)
            logger.exception("llama-server restart raised")

    @staticmethod
    def _endpoint_ready(endpoint: str) -> bool:
        host, _, port = endpoint.rpartition(":")
        try:
            return _tcp_ready(host, int(port))
        except ValueError:
            return False

    def _wait_for_rpc_ready(
        self, endpoints: list[str], timeout: float
    ) -> tuple[list[str], dict[str, str]]:
        """Wait until each RPC endpoint accepts TCP, up to ``timeout`` total.

        Returns (ready_endpoints, excluded_endpoint -> reason). Order of the
        ready list preserves the input (and therefore --rpc/device) order.
        """
        deadline = time.monotonic() + timeout
        remaining = list(endpoints)
        reached: set[str] = set()
        while True:  # always probe at least once, even with timeout=0
            still_pending: list[str] = []
            for ep in remaining:
                if self._endpoint_ready(ep):
                    reached.add(ep)
                else:
                    still_pending.append(ep)
            remaining = still_pending
            if not remaining or time.monotonic() >= deadline:
                break
            time.sleep(0.5)
        ready = [ep for ep in endpoints if ep in reached]
        excluded = {
            ep: f"RPC port not reachable within {timeout:.0f}s"
            for ep in endpoints
            if ep not in reached
        }
        return ready, excluded

    def _probe_devices(self, binary: str, rpc_endpoints: list[str]):
        """Indirection point so tests can inject fake device listings."""
        # Keep the probe short: a long probe blocks llama-server startup and
        # looks like "loading model" forever in chat. If it doesn't return
        # quickly we fall back to llama.cpp's default split (just --rpc).
        timeout = 15.0
        return probe_llama_devices(binary, rpc_endpoints, timeout=timeout)

    def _apply_distribution(
        self,
        dist,
        binary: str,
        rpc_endpoints: list[str],
        tensor_split: str | None,
    ) -> str | None:
        """Probe devices and compute tensor_split.

        On probe failure we do NOT synthesize a split — we fall back to
        llama.cpp's default proportional split (just ``--rpc``, no
        ``--tensor-split``), which is the fast path that always worked.
        The distribution policy only applies when the probe succeeds quickly.
        """
        probed = self._probe_devices(binary, rpc_endpoints)
        if probed is None:
            self._fallback_reason = (
                "device probe failed; using llama.cpp default proportional split"
            )
            logger.warning(self._fallback_reason)
            return tensor_split

        result = compute_allocation(
            dist,
            probed,
            self.config.node_id,
            worker_caps=self._worker_caps,
            rtt_ms_by_host=self._worker_rtt,
        )
        self._last_devices = result.devices
        self._fallback_reason = result.fallback_reason
        for alloc in result.devices:
            if alloc.excluded_reason:
                logger.warning(
                    "Device %s excluded from allocation: %s",
                    alloc.name,
                    alloc.excluded_reason,
                )
            else:
                logger.info(
                    "Device %s (%s, %s): free %.1f GB, usable %.1f GB, "
                    "weight %.4f (%.1f%% of model tensors, estimated)",
                    alloc.name,
                    alloc.kind,
                    alloc.memory_type,
                    alloc.free_gb or 0.0,
                    alloc.usable_gb,
                    alloc.weight,
                    alloc.share_percent or 0.0,
                )
        if self.config.inference.tensor_split:
            logger.info(
                "inference.tensor_split is set explicitly; overriding computed split"
            )
            return tensor_split
        return result.tensor_split or tensor_split

    def rpc_server_devices(self) -> list[str]:
        """Devices the local ggml-rpc-server exposes, parsed from its startup
        banner in the log file (measured; empty when unknown)."""
        if self.rpc_server is None or self.rpc_server.log_path is None:
            return []
        try:
            data = self.rpc_server.log_path.read_bytes()
        except OSError:
            return []
        text = data[-8000:].decode("utf-8", errors="replace")
        return [d.name for d in parse_device_listing(text)]

    def distribution_diagnostics(
        self,
        active_requests: int = 0,
        local_capabilities: NodeCapabilities | None = None,
    ) -> DistributionDiagnostics:
        dist = self.config.inference.distribution
        return DistributionDiagnostics(
            policy=dist.policy if dist else None,
            backend=self.config.inference.backend,
            tensor_split=self._last_tensor_split,
            devices=self._last_devices,
            rpc_endpoints=self.rpc_endpoints_effective(),
            launched_rpc_endpoints=self._launched_endpoints,
            excluded_endpoints=self._excluded_endpoints,
            topology_stale=self.topology_stale,
            restart_state=self._restart_state,
            restart_error=self._restart_error,
            effective_command=self._effective_command,
            fallback_reason=self._fallback_reason,
            active_requests=active_requests,
            local_capabilities=local_capabilities,
            workers=self._worker_caps,
        )

    def _ensure_process_running(
        self, proc: ManagedProcess, start_fn: Callable[[], None], *, should_run: bool
    ) -> None:
        if not should_run:
            return
        state = proc.refresh_state()
        if state != ProcessState.FAILED:
            return

        now = time.monotonic()
        history = self._restart_timestamps[proc.name]
        while history and now - history[0] > self._restart_window_seconds:
            history.popleft()

        if len(history) >= self.config.inference.max_restarts:
            proc.last_error = (
                f"{proc.name} exceeded restart budget "
                f"({self.config.inference.max_restarts} in 10 minutes): {proc.last_error or 'unknown'}"
            )
            logger.error(proc.last_error)
            return

        backoff = self._restart_backoff.get(proc.name, 0.5)
        logger.warning("Restarting %s after failure (backoff %.2fs)", proc.name, backoff)
        time.sleep(backoff)
        start_fn()
        history.append(time.monotonic())
        self._restart_backoff[proc.name] = min(backoff * 2, 30.0)

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
        rpc_endpoints = self.rpc_endpoints_effective()
        tensor_split = inf.tensor_split
        self._excluded_endpoints = {}
        self._last_devices = []
        self._fallback_reason = None

        dist = inf.distribution
        if dist is not None:
            rpc_endpoints, excluded = self._wait_for_rpc_ready(
                rpc_endpoints, dist.wait_for_workers_seconds
            )
            self._excluded_endpoints = excluded
            for ep, reason in excluded.items():
                logger.warning("Excluding RPC endpoint %s: %s", ep, reason)

            tensor_split = self._apply_distribution(dist, binary, rpc_endpoints, tensor_split)

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

        if rpc_endpoints:
            cmd.extend(["--rpc", ",".join(rpc_endpoints)])
        if tensor_split:
            cmd.extend(["--tensor-split", tensor_split])
        if inf.extra_args:
            cmd.extend(inf.extra_args)

        self._launched_endpoints = list(rpc_endpoints)
        self._last_tensor_split = tensor_split
        self._effective_command = redact_command(cmd)
        logger.info("Effective llama-server command: %s", " ".join(self._effective_command))

        self.llama_server = ManagedProcess(
            name="llama-server", command=cmd, log_path=self._log_path("llama-server")
        )
        self.llama_server.start()
