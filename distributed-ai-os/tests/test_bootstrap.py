"""Installer orchestration tests: token, redaction, install/repeat/uninstall, health."""

from __future__ import annotations

import argparse
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from daios_launcher import bootstrap, paths, system_check
from daios_launcher.settings import LauncherSettings


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point the whole install layout at a tmp dir with a space in the path."""
    home = tmp_path / "Local App" / "BSDK"
    monkeypatch.setenv("DAIOS_HOME", str(home))
    monkeypatch.setattr("daios_launcher.settings.SETTINGS_PATH", tmp_path / "launcher.json")
    monkeypatch.setattr(bootstrap, "_pause", lambda *a, **k: None)
    return home


def _args(**over) -> argparse.Namespace:
    base = dict(
        token=None, dev=False, verbose=False, auto_install=False,
        install_dir=Path("x"), repo="r", branch="main",
    )
    base.update(over)
    return argparse.Namespace(**base)


def _supported_report() -> system_check.SystemReport:
    return system_check.SystemReport(
        supported=True, unsupported_reason=None, os_name="Windows", os_version="10.0.22631",
        os_release="11", architecture="AMD64", is_windows=True, is_x64=True, cpu_count=8,
        ram_total_gb=16.0, ram_available_gb=8.0, disk_free_gb=100.0, network_ok=True,
        ports=[system_check.PortStatus(port=p, in_use=False) for p in system_check.REQUIRED_PORTS],
        already_installed=False, already_running=False,
    )


def test_resolve_token_precedence(isolated, monkeypatch):
    s = LauncherSettings()
    monkeypatch.delenv(bootstrap.TOKEN_ENV, raising=False)
    assert bootstrap._resolve_token("cli-token", s) == "cli-token"
    monkeypatch.setenv(bootstrap.TOKEN_ENV, "env-token")
    assert bootstrap._resolve_token(None, LauncherSettings()) == "env-token"
    monkeypatch.delenv(bootstrap.TOKEN_ENV, raising=False)
    s2 = LauncherSettings(cluster_token="stored")
    assert bootstrap._resolve_token(None, s2) == "stored"
    generated = bootstrap._resolve_token(None, LauncherSettings())
    assert len(generated) > 20  # auto-generated when nothing supplied


def test_redact_filter_hides_token():
    import logging

    f = bootstrap._RedactFilter("supersecret")
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "token=supersecret here", (), None)
    f.filter(rec)
    assert "supersecret" not in rec.getMessage()
    rec2 = logging.LogRecord("x", logging.INFO, __file__, 1, "val=%s", ("supersecret",), None)
    f.filter(rec2)
    assert "supersecret" not in rec2.getMessage()


def test_health_ok_true_and_false(isolated):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        assert bootstrap._health_ok(port, timeout=5.0) is True
    finally:
        srv.shutdown()
    # Nothing listening now -> False (short timeout).
    assert bootstrap._health_ok(port, timeout=2.0) is False


def _patch_install(monkeypatch, *, already_installed=False):
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    report = _supported_report().model_copy(update={"already_installed": already_installed})
    monkeypatch.setattr(bootstrap.system_check, "check_system", lambda *a, **k: report)

    def fake_backend():
        paths.bin_dir().mkdir(parents=True, exist_ok=True)
        rpc = paths.bin_dir() / "ggml-rpc-server.exe"
        rpc.write_bytes(b"real binary")
        return rpc

    monkeypatch.setattr(bootstrap, "ensure_real_backend", fake_backend)
    monkeypatch.setattr(bootstrap, "_copy_self_to_install", lambda exe: None)
    monkeypatch.setattr(bootstrap, "install_task", lambda exe: (True, "Task installed"))
    monkeypatch.setattr(bootstrap, "_spawn_service_detached", lambda exe: None)
    monkeypatch.setattr(bootstrap, "_stop_running_worker", lambda: None)
    monkeypatch.setattr(bootstrap, "_health_ok", lambda *a, **k: True)
    monkeypatch.setattr(bootstrap, "is_windows", lambda: True)


def test_fresh_install_succeeds(isolated, monkeypatch):
    _patch_install(monkeypatch)
    rc = bootstrap.install_or_update(None, dev=False, verbose=False, args=_args())
    assert rc == 0
    s = LauncherSettings.load()
    assert s.role == "worker"
    assert s.autostart_node is True
    assert s.cluster_token and len(s.cluster_token) > 20
    assert (paths.bin_dir() / "ggml-rpc-server.exe").is_file()


def test_repeat_install_is_idempotent(isolated, monkeypatch):
    _patch_install(monkeypatch)
    assert bootstrap.install_or_update(None, dev=False, verbose=False, args=_args()) == 0
    # Second run: now already installed -> update path, must still succeed.
    report2 = _supported_report().model_copy(update={"already_installed": True})
    monkeypatch.setattr(bootstrap.system_check, "check_system", lambda *a, **k: report2)
    assert bootstrap.install_or_update(None, dev=False, verbose=False, args=_args()) == 0


def test_install_refuses_without_real_backend(isolated, monkeypatch):
    _patch_install(monkeypatch)

    def boom():
        raise bootstrap.artifacts.MissingBinaryError("no verified binary")

    monkeypatch.setattr(bootstrap, "ensure_real_backend", boom)
    rc = bootstrap.install_or_update(None, dev=False, verbose=False, args=_args())
    assert rc == 3  # fails loudly, does not mock-fallback


def test_uninstall_preserves_then_purges(isolated, monkeypatch):
    paths.ensure_layout()
    marker = paths.install_root() / "keepme.txt"
    marker.write_text("data")
    monkeypatch.setattr(bootstrap, "_stop_running_worker", lambda: None)
    monkeypatch.setattr(bootstrap, "uninstall_task", lambda: (True, "removed"))
    monkeypatch.setattr(bootstrap, "is_windows", lambda: True)

    assert bootstrap.uninstall(purge=False) == 0
    assert marker.exists()  # data preserved without --purge

    assert bootstrap.uninstall(purge=True) == 0
    assert not paths.install_root().exists()  # purged


def test_worker_auto_configuration_ports():
    from daios_launcher.config_gen import build_node_config, StartRequest
    from daios_protocol.config import NodeRole

    req = StartRequest(
        role=NodeRole.WORKER, backend="mock", api_port=8001, rpc_port=50052,
        discovery_enabled=True,
    )
    config = build_node_config(req, node_id="worker-auto")
    assert config.network.api_port == 8001
    assert config.network.rpc_port == 50052
    assert config.discovery.enabled is True
    assert config.network.bind_host == "0.0.0.0"  # LAN-reachable


def test_frozen_rpc_binary_resolves_to_bin_dir(isolated, monkeypatch):
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    from daios_launcher.config_gen import _runtime_binary

    resolved = Path(_runtime_binary(Path("ignored"), "ggml-rpc-server"))
    assert resolved.parent == paths.bin_dir()
