"""InferenceManager distribution wiring: launch flags, readiness, topology."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from daios_node.allocation import ProbedDevice
from daios_node.inference import InferenceManager, ManagedProcess
from daios_protocol.config import NodeConfig
from daios_protocol.health import NodeCapabilities, ProcessState

# Every llama-server flag the manager is allowed to emit. Guards against
# generating flags the bundled llama.cpp build does not support.
_SUPPORTED_LLAMA_FLAGS = {
    "--host",
    "--port",
    "-ngl",
    "-c",
    "-m",
    "-t",
    "-tb",
    "-np",
    "--cont-batching",
    "--mlock",
    "--rpc",
    "--tensor-split",
}


class _FakeRunningProc:
    """Stands in for a live subprocess.Popen."""

    def poll(self):
        return None

    def send_signal(self, _sig):
        return None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        return None


def _running_llama(command: list[str] | None = None) -> ManagedProcess:
    proc = ManagedProcess(name="llama-server", command=command or ["llama-server"])
    proc.process = _FakeRunningProc()
    proc.state = ProcessState.RUNNING
    return proc


def _coordinator_config(distribution: dict | None = None, **overrides) -> NodeConfig:
    inference = {
        "backend": "llama.cpp",
        "model_path": "model.gguf",
        "llama_server_bin": "llama-server",
    }
    if distribution is not None:
        inference["distribution"] = distribution
    raw = {
        "node_id": "coord-1",
        "role": "coordinator",
        "inference": inference,
        "peers": [{"id": "w1", "host": "10.0.0.2", "rpc_port": 50052}],
    }
    raw.update(overrides)
    return NodeConfig.model_validate(raw)


_FAST_DIST = {
    "policy": "auto",
    "wait_for_workers_seconds": 0.0,
    "restart_debounce_seconds": 0.0,
    "coordinator_reserve_vram_gb": 0.0,
    "worker_reserve_ram_gb": 0.0,
    "worker_reserve_vram_gb": 0.0,
}


def _probed_two_devices(*_args, **_kwargs):
    return [
        ProbedDevice(name="CUDA0", description="Local", total_mib=24576, free_mib=24576),
        ProbedDevice(
            name="RPC[10.0.0.2:50052]", description="RPC", total_mib=8192, free_mib=8192
        ),
    ]


def test_legacy_config_command_is_unchanged_and_never_probes():
    manager = InferenceManager(_coordinator_config(distribution=None))

    def _explode(*_a, **_k):
        raise AssertionError("legacy path must not probe devices")

    manager._probe_devices = _explode  # type: ignore[method-assign]
    with patch("daios_node.inference.subprocess.Popen"):
        manager._start_llama_server()

    cmd = manager.llama_server.command
    assert "--rpc" in cmd
    assert cmd[cmd.index("--rpc") + 1] == "10.0.0.2:50052"
    assert "--tensor-split" not in cmd


def test_distribution_adds_computed_tensor_split():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))
    manager._probe_devices = _probed_two_devices  # type: ignore[method-assign]
    manager.set_worker_capabilities(
        {"10.0.0.2": NodeCapabilities(node_id="w1", gpu_available=True, rpc_devices=["CUDA0"])}
    )
    with (
        patch("daios_node.inference.subprocess.Popen"),
        patch("daios_node.inference._tcp_ready", return_value=True),
    ):
        manager._start_llama_server()

    cmd = manager.llama_server.command
    assert "--tensor-split" in cmd
    split = cmd[cmd.index("--tensor-split") + 1]
    parts = [float(p) for p in split.split(",")]
    assert len(parts) == 2
    assert parts[0] == pytest.approx(0.75, abs=0.01)  # 24 GB vs 8 GB, both VRAM
    assert parts[1] == pytest.approx(0.25, abs=0.01)
    assert manager.distribution_diagnostics().tensor_split == split


def test_explicit_tensor_split_overrides_computed():
    config = _coordinator_config(distribution=_FAST_DIST)
    config.inference.tensor_split = "1,9"
    manager = InferenceManager(config)
    manager._probe_devices = _probed_two_devices  # type: ignore[method-assign]
    with (
        patch("daios_node.inference.subprocess.Popen"),
        patch("daios_node.inference._tcp_ready", return_value=True),
    ):
        manager._start_llama_server()
    cmd = manager.llama_server.command
    assert cmd[cmd.index("--tensor-split") + 1] == "1,9"


def test_only_supported_llama_flags_are_generated():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))
    manager._probe_devices = _probed_two_devices  # type: ignore[method-assign]
    with (
        patch("daios_node.inference.subprocess.Popen"),
        patch("daios_node.inference._tcp_ready", return_value=True),
    ):
        manager._start_llama_server()
    flags = {arg for arg in manager.llama_server.command if arg.startswith("-")}
    assert flags <= _SUPPORTED_LLAMA_FLAGS


def test_unreachable_worker_is_excluded_from_rpc_flag():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))
    manager._probe_devices = lambda *_a, **_k: [
        ProbedDevice(name="CUDA0", description="Local", total_mib=24576, free_mib=24576)
    ]
    with (
        patch("daios_node.inference.subprocess.Popen"),
        patch("daios_node.inference._tcp_ready", return_value=False),
    ):
        manager._start_llama_server()

    cmd = manager.llama_server.command
    assert "--rpc" not in cmd
    diag = manager.distribution_diagnostics()
    assert "10.0.0.2:50052" in diag.excluded_endpoints
    assert "not reachable" in diag.excluded_endpoints["10.0.0.2:50052"]


def test_probe_failure_falls_back_to_default_split():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))
    manager._probe_devices = lambda *_a, **_k: None  # type: ignore[method-assign]
    with (
        patch("daios_node.inference.subprocess.Popen"),
        patch("daios_node.inference._tcp_ready", return_value=True),
    ):
        manager._start_llama_server()
    cmd = manager.llama_server.command
    assert "--rpc" in cmd
    # Probe failed → no tensor-split, fall back to llama.cpp default split
    # (the fast path that always worked). Don't synthesize a risky split.
    assert "--tensor-split" not in cmd
    assert "probe failed" in manager.distribution_diagnostics().fallback_reason


def test_secrets_in_extra_args_redacted_in_diagnostics_but_not_process():
    config = _coordinator_config(distribution=None)
    config.inference.extra_args = ["--api-key", "super-secret-token"]
    manager = InferenceManager(config)
    with patch("daios_node.inference.subprocess.Popen"):
        manager._start_llama_server()

    # The real process still receives the secret...
    assert "super-secret-token" in manager.llama_server.command
    # ...but diagnostics and logs never expose it.
    diag = manager.distribution_diagnostics()
    assert "super-secret-token" not in " ".join(diag.effective_command)
    assert "***" in diag.effective_command


# ---------------------------------------------------------------------------
# Topology lifecycle
# ---------------------------------------------------------------------------


def test_set_peer_hosts_does_not_restart_inline():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))
    manager.llama_server = _running_llama()
    manager._launched_endpoints = ["10.0.0.2:50052"]
    original = manager.llama_server

    manager.set_peer_hosts(["10.0.0.2", "10.0.0.9"])
    assert manager.llama_server is original  # untouched
    assert manager.topology_stale


def test_stale_topology_detection_on_worker_departure():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))
    manager.llama_server = _running_llama()
    manager._launched_endpoints = ["10.0.0.2:50052", "10.0.0.9:50052"]
    manager.set_peer_hosts(["10.0.0.2"])
    assert manager.topology_stale


def test_restart_waits_for_active_requests():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))
    manager.llama_server = _running_llama()
    manager._launched_endpoints = []
    manager.set_peer_hosts(["10.0.0.2"])

    restarted = []
    manager._start_llama_server = lambda: restarted.append(True)  # type: ignore[method-assign]
    with patch("daios_node.inference._tcp_ready", return_value=True):
        manager.maybe_apply_topology(active_requests=2)
    assert not restarted
    assert manager.distribution_diagnostics().restart_state == "pending"


def test_restart_debounce_prevents_flapping():
    dist = dict(_FAST_DIST, restart_debounce_seconds=300.0)
    manager = InferenceManager(_coordinator_config(distribution=dist))
    manager.llama_server = _running_llama()
    manager._launched_endpoints = []
    manager.set_peer_hosts(["10.0.0.2"])

    restarted = []
    manager._start_llama_server = lambda: restarted.append(True)  # type: ignore[method-assign]
    manager.maybe_apply_topology(active_requests=0)
    assert not restarted
    assert manager.distribution_diagnostics().restart_state == "pending"


def test_restart_skipped_while_new_worker_unreachable():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))
    manager.llama_server = _running_llama()
    manager._launched_endpoints = []
    manager.set_peer_hosts(["10.0.0.2"])

    restarted = []
    manager._start_llama_server = lambda: restarted.append(True)  # type: ignore[method-assign]
    with patch("daios_node.inference._tcp_ready", return_value=False):
        manager.maybe_apply_topology(active_requests=0)
    assert not restarted
    assert manager.distribution_diagnostics().restart_state == "pending"


def test_safe_restart_applies_when_idle_and_reachable():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))
    manager.llama_server = _running_llama()
    manager._launched_endpoints = []
    manager.set_peer_hosts(["10.0.0.2"])

    def _fake_start() -> None:
        manager.llama_server = _running_llama()
        manager._launched_endpoints = manager.rpc_endpoints_effective()

    manager._start_llama_server = _fake_start  # type: ignore[method-assign]
    with patch("daios_node.inference._tcp_ready", return_value=True):
        manager.maybe_apply_topology(active_requests=0)

    diag = manager.distribution_diagnostics()
    assert diag.restart_state == "success"
    assert not diag.topology_stale


def test_request_reload_bypasses_debounce_but_waits_for_requests():
    dist = dict(_FAST_DIST, restart_debounce_seconds=300.0)
    manager = InferenceManager(_coordinator_config(distribution=dist))
    manager.llama_server = _running_llama()
    manager._launched_endpoints = ["10.0.0.2:50052"]

    assert manager.request_reload() == "pending"

    restarted = []

    def _fake_start() -> None:
        restarted.append(True)
        manager.llama_server = _running_llama()
        manager._launched_endpoints = manager.rpc_endpoints_effective()

    manager._start_llama_server = _fake_start  # type: ignore[method-assign]
    manager.maybe_apply_topology(active_requests=1)
    assert not restarted  # still draining

    manager.maybe_apply_topology(active_requests=0)
    assert restarted
    assert manager.distribution_diagnostics().restart_state == "success"


def test_gen2_deferred_start_waits_for_discovery():
    config = _coordinator_config(
        distribution=dict(_FAST_DIST, wait_for_workers_seconds=60.0),
        peers=[],
        discovery={"enabled": True},
    )
    manager = InferenceManager(config)
    started = []
    manager._start_rpc_server = lambda: None  # type: ignore[method-assign]
    manager._start_llama_server = lambda: started.append(True)  # type: ignore[method-assign]

    manager.start()
    assert not started  # deferred: no workers known yet
    assert manager.topology_stale  # pending initial start

    manager.maybe_apply_topology(active_requests=0)
    assert not started  # deadline not reached, still no workers

    manager.set_peer_hosts(["10.0.0.2"])
    manager.maybe_apply_topology(active_requests=0)
    assert started  # worker discovered -> start now


def test_gen2_deferred_start_times_out_to_solo():
    config = _coordinator_config(
        distribution=dict(_FAST_DIST, wait_for_workers_seconds=0.0),
        peers=[],
        discovery={"enabled": True},
    )
    manager = InferenceManager(config)
    started = []
    manager._start_rpc_server = lambda: None  # type: ignore[method-assign]
    manager._start_llama_server = lambda: started.append(True)  # type: ignore[method-assign]

    manager.start()
    manager.maybe_apply_topology(active_requests=0)
    assert started  # grace expired -> solo start


def test_mock_backend_never_restarts_or_goes_stale():
    config = NodeConfig.model_validate(
        {
            "node_id": "coord-1",
            "role": "coordinator",
            "inference": {"backend": "mock"},
            "peers": [{"id": "w1", "host": "10.0.0.2"}],
        }
    )
    manager = InferenceManager(config)
    manager.set_peer_hosts(["10.0.0.5"])
    assert not manager.topology_stale
    manager.maybe_apply_topology(active_requests=0)  # no-op, must not raise
    assert manager.rpc_endpoints_effective() == ["10.0.0.5:50052"]


def test_rpc_server_devices_parsed_from_log(tmp_path):
    manager = InferenceManager(_coordinator_config())
    log = tmp_path / "rpc.log"
    log.write_text(
        "Starting RPC server v3.0.0\nDevices:\n"
        "  CUDA0: NVIDIA GeForce RTX 5090 (32109 MiB, 31588 MiB free)\n"
    )
    manager.rpc_server = ManagedProcess(name="rpc-server", command=["x"], log_path=log)
    assert manager.rpc_server_devices() == ["CUDA0"]


def test_wait_for_rpc_ready_partitions_endpoints():
    manager = InferenceManager(_coordinator_config(distribution=_FAST_DIST))

    def _ready(host, port, timeout=1.0):
        return host == "10.0.0.2"

    with patch("daios_node.inference._tcp_ready", side_effect=_ready):
        ready, excluded = manager._wait_for_rpc_ready(
            ["10.0.0.2:50052", "10.0.0.3:50052"], timeout=0.1
        )
    assert ready == ["10.0.0.2:50052"]
    assert list(excluded) == ["10.0.0.3:50052"]
