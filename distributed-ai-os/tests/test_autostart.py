"""Tests for the login autostart task (command correctness + idempotency)."""

from __future__ import annotations

from pathlib import Path


from daios_launcher import autostart_windows as aw


def test_task_command_quotes_spaces_and_uses_service():
    exe = Path(r"C:\Users\Jane Doe\AppData\Local\BSDK\daios-worker.exe")
    cmd = aw._task_command(exe)
    assert cmd == f'"{exe}" --service'
    assert "--no-window" not in cmd  # the old broken flag is gone


def test_install_task_idempotent_when_current(monkeypatch):
    exe = Path(r"C:\BSDK\daios-worker.exe")
    monkeypatch.setattr(aw, "is_windows", lambda: True)
    monkeypatch.setattr(aw, "current_task_command", lambda: f'"{exe}" --service')

    called = {"run": False}

    def fake_run(*a, **k):
        called["run"] = True
        raise AssertionError("schtasks should not run when task is current")

    monkeypatch.setattr(aw.subprocess, "run", fake_run)
    ok, msg = aw.install_task(exe)
    assert ok is True
    assert "current" in msg.lower()
    assert called["run"] is False


def test_install_task_creates_with_force_and_installed_path(monkeypatch):
    exe = Path(r"C:\Program Files\BSDK\daios-worker.exe")
    monkeypatch.setattr(aw, "is_windows", lambda: True)
    monkeypatch.setattr(aw, "current_task_command", lambda: None)
    captured = {}

    class R:
        returncode = 0
        stdout = "SUCCESS"
        stderr = ""

    def fake_run(cmd, **k):
        captured["cmd"] = cmd
        return R()

    monkeypatch.setattr(aw.subprocess, "run", fake_run)
    ok, msg = aw.install_task(exe)
    assert ok is True
    cmd = captured["cmd"]
    assert "/Create" in cmd and "/F" in cmd  # /F prevents duplicates
    assert f'"{exe}" --service' in cmd  # installed exe path, quoted
    assert "ONLOGON" in cmd


def test_uninstall_task_success(monkeypatch):
    monkeypatch.setattr(aw, "is_windows", lambda: True)

    class R:
        returncode = 0
        stdout = "SUCCESS: deleted"
        stderr = ""

    monkeypatch.setattr(aw.subprocess, "run", lambda *a, **k: R())
    ok, msg = aw.uninstall_task()
    assert ok is True


def test_uninstall_task_missing_is_ok(monkeypatch):
    monkeypatch.setattr(aw, "is_windows", lambda: True)

    class R:
        returncode = 1
        stdout = ""
        stderr = "ERROR: The system cannot find the file specified."

    monkeypatch.setattr(aw.subprocess, "run", lambda *a, **k: R())
    ok, _ = aw.uninstall_task()
    assert ok is True  # absent task is treated as already-removed
