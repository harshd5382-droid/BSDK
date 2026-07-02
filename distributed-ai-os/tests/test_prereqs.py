"""Tests for the dev-path prerequisite checks (Git/Python versions + winget)."""

from __future__ import annotations


from daios_launcher import prereqs


def test_python_missing(monkeypatch):
    monkeypatch.setattr(prereqs, "find_tool", lambda *a: None)
    info = prereqs.check_python()
    assert not info.ok
    assert "not found" in info.reason


def test_python_too_old(monkeypatch):
    monkeypatch.setattr(prereqs, "find_tool", lambda *a: "C:\\py\\python.exe")
    monkeypatch.setattr(prereqs, "_run", lambda *a, **k: (0, "Python 3.9.1"))
    info = prereqs.check_python()
    assert not info.ok
    assert "too old" in info.reason
    assert info.version == (3, 9, 1)


def test_python_ok(monkeypatch):
    monkeypatch.setattr(prereqs, "find_tool", lambda *a: "C:\\py\\python.exe")
    monkeypatch.setattr(prereqs, "_run", lambda *a, **k: (0, "Python 3.12.4"))
    info = prereqs.check_python()
    assert info.ok
    assert info.version == (3, 12, 4)


def test_git_missing(monkeypatch):
    monkeypatch.setattr(prereqs, "find_tool", lambda *a: None)
    info = prereqs.check_git()
    assert not info.ok
    assert "not found" in info.reason


def test_ensure_dev_prerequisites_reports_without_installing(monkeypatch):
    monkeypatch.setattr(prereqs, "check_git", lambda: prereqs.ToolInfo("Git", reason="Git not found", winget_id=prereqs.WINGET_GIT))
    monkeypatch.setattr(prereqs, "check_python", lambda: prereqs.ToolInfo("Python", ok=True))
    messages: list[str] = []
    ok, tools = prereqs.ensure_dev_prerequisites(
        auto_install=False, on_message=messages.append
    )
    assert ok is False
    assert any("winget install" in m for m in messages)


def test_winget_unavailable_message(monkeypatch):
    monkeypatch.setattr(prereqs, "winget_available", lambda: False)
    messages: list[str] = []
    result = prereqs.winget_install("Git.Git", on_message=messages.append)
    assert result is False
    assert any("winget is unavailable" in m for m in messages)


def test_auto_install_blocked_when_winget_missing(monkeypatch):
    monkeypatch.setattr(prereqs, "check_git", lambda: prereqs.ToolInfo("Git", reason="Git not found"))
    monkeypatch.setattr(prereqs, "check_python", lambda: prereqs.ToolInfo("Python", ok=True))
    monkeypatch.setattr(prereqs, "winget_available", lambda: False)
    messages: list[str] = []
    ok, _ = prereqs.ensure_dev_prerequisites(auto_install=True, on_message=messages.append)
    assert ok is False
    assert any("winget is unavailable" in m for m in messages)
