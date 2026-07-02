"""Tests for the Windows firewall rules (command correctness + idempotency)."""

from __future__ import annotations

from pathlib import Path

from daios_launcher import firewall_windows as fw

WORKER = Path(r"C:\Users\Jane Doe\AppData\Local\BSDK\daios-worker.exe")
RPC = Path(r"C:\Users\Jane Doe\AppData\Local\BSDK\bin\ggml-rpc-server.exe")


def test_worker_rules_cover_mdns_api_and_rpc():
    rules = fw.worker_rules(WORKER, RPC)
    by_name = {r.name: r for r in rules}
    assert set(by_name) == {
        "BSDK Worker (TCP-In)",
        "BSDK Worker (mDNS-In)",
        "BSDK GGML RPC (TCP-In)",
    }
    mdns = by_name["BSDK Worker (mDNS-In)"]
    assert mdns.protocol == "UDP"
    assert mdns.localport == "5353"
    assert mdns.program == WORKER
    assert by_name["BSDK GGML RPC (TCP-In)"].program == RPC


def test_add_command_is_inbound_allow_scoped_to_private_profiles():
    rule = fw.worker_rules(WORKER, RPC)[0]
    cmd = rule.add_command()
    assert cmd[:5] == ["netsh", "advfirewall", "firewall", "add", "rule"]
    assert "dir=in" in cmd
    assert "action=allow" in cmd
    assert f"program={WORKER}" in cmd
    # Never open the unauthenticated RPC protocol on public networks.
    assert "profile=private,domain" in cmd
    assert not any(p.startswith("localport=") for p in cmd)


def test_mdns_rule_includes_localport():
    mdns = next(r for r in fw.worker_rules(WORKER, RPC) if "mDNS" in r.name)
    assert "localport=5353" in mdns.add_command()


def test_ensure_rules_noop_when_all_present(monkeypatch):
    monkeypatch.setattr(fw, "is_windows", lambda: True)
    monkeypatch.setattr(fw, "rule_exists", lambda name: True)

    def fail_run(*a, **k):
        raise AssertionError("netsh should not run when rules exist")

    monkeypatch.setattr(fw.subprocess, "run", fail_run)
    ok, msg = fw.ensure_rules(WORKER, RPC)
    assert ok is True
    assert "already" in msg.lower()


def test_ensure_rules_adds_missing_directly_when_elevated(monkeypatch):
    monkeypatch.setattr(fw, "is_windows", lambda: True)
    monkeypatch.setattr(fw, "rule_exists", lambda name: "mDNS" not in name)
    ran: list[list[str]] = []

    class R:
        returncode = 0
        stdout = "Ok."
        stderr = ""

    def fake_run(cmd, **k):
        ran.append(cmd)
        return R()

    monkeypatch.setattr(fw.subprocess, "run", fake_run)
    ok, msg = fw.ensure_rules(WORKER, RPC)
    assert ok is True
    assert len(ran) == 1
    assert "name=BSDK Worker (mDNS-In)" in ran[0]


def test_ensure_rules_falls_back_to_elevation_then_instructions(monkeypatch):
    monkeypatch.setattr(fw, "is_windows", lambda: True)
    monkeypatch.setattr(fw, "rule_exists", lambda name: False)

    class Denied:
        returncode = 1
        stdout = ""
        stderr = "The requested operation requires elevation."

    monkeypatch.setattr(fw.subprocess, "run", lambda *a, **k: Denied())
    monkeypatch.setattr(fw, "_run_elevated_batch", lambda cmds: False)
    ok, msg = fw.ensure_rules(WORKER, RPC)
    assert ok is False
    assert "netsh advfirewall firewall add rule" in msg


def test_ensure_rules_elevated_batch_success(monkeypatch):
    monkeypatch.setattr(fw, "is_windows", lambda: True)
    state = {"added": False}
    monkeypatch.setattr(fw, "rule_exists", lambda name: state["added"])

    class Denied:
        returncode = 1
        stdout = ""
        stderr = "elevation required"

    monkeypatch.setattr(fw.subprocess, "run", lambda *a, **k: Denied())

    def fake_elevated(cmds):
        state["added"] = True
        return True

    monkeypatch.setattr(fw, "_run_elevated_batch", fake_elevated)
    ok, msg = fw.ensure_rules(WORKER, RPC)
    assert ok is True
    assert "elevated" in msg.lower()


def test_remove_rules_noop_when_absent(monkeypatch):
    monkeypatch.setattr(fw, "is_windows", lambda: True)
    monkeypatch.setattr(fw, "rule_exists", lambda name: False)
    ok, msg = fw.remove_rules()
    assert ok is True
    assert "no firewall rules" in msg.lower()


def test_non_windows_is_a_safe_noop(monkeypatch):
    monkeypatch.setattr(fw, "is_windows", lambda: False)
    ok, _ = fw.ensure_rules(WORKER, RPC)
    assert ok is False
    ok, _ = fw.remove_rules()
    assert ok is False
    assert fw.rule_exists("anything") is False
    assert fw.active_profile_is_public() is False
