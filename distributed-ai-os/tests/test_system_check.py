"""System detection / unsupported-OS validation tests."""

from __future__ import annotations

import socket


from daios_launcher import system_check


def test_unsupported_on_non_windows(monkeypatch):
    monkeypatch.setattr(system_check.sys, "platform", "linux")
    reason = system_check._detect_unsupported()
    assert reason is not None
    assert "Windows only" in reason


def test_unsupported_on_arm(monkeypatch):
    monkeypatch.setattr(system_check.sys, "platform", "win32")
    monkeypatch.setattr(system_check.platform, "machine", lambda: "ARM64")
    reason = system_check._detect_unsupported()
    assert reason is not None
    assert "architecture" in reason.lower()


def test_supported_on_windows_x64(monkeypatch):
    monkeypatch.setattr(system_check.sys, "platform", "win32")
    monkeypatch.setattr(system_check.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(system_check.platform, "release", lambda: "10")
    assert system_check._detect_unsupported() is None


def test_report_blocking_errors_low_ram(monkeypatch):
    report = system_check.check_system(probe_network=False)
    # Force a low-RAM clone and assert it surfaces as a blocking error.
    low = report.model_copy(update={"ram_total_gb": 0.5, "supported": True})
    errors = low.blocking_errors()
    assert any("RAM" in e for e in errors)


def test_port_in_use_detects_bound_socket():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert system_check.port_in_use(port, host="127.0.0.1") is True
    # After close the port should be free again.
    assert system_check.port_in_use(port, host="127.0.0.1") is False


def test_check_system_smoke():
    report = system_check.check_system(probe_network=False)
    assert report.cpu_count >= 1
    assert report.ram_total_gb > 0
    assert {p.port for p in report.ports} == set(system_check.REQUIRED_PORTS)
    text = system_check.format_report(report)
    assert "system check" in text.lower()
