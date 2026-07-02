"""Windows Defender Firewall rules for the worker.

mDNS auto-discovery and GGML RPC require *inbound* traffic that Windows blocks
by default for per-user programs: UDP 5353 (mDNS announcements/queries) and TCP
to the worker exe (node API + launcher control), plus TCP to
``ggml-rpc-server.exe`` (the RPC port). Without these rules the coordinator
never hears the worker's mDNS advertisement — auto-discovery silently fails and
users are forced to type IPs manually.

Checking whether rules exist works without elevation; adding or removing them
does not. ``ensure_rules`` therefore checks first, tries ``netsh`` directly (in
case the process is already elevated), and finally falls back to a single
UAC-prompted elevated helper. Declining the UAC prompt is not fatal — the
worker still runs, and the caller prints the manual commands.

Rules are scoped to the private/domain profiles: the RPC protocol is an
unauthenticated LAN protocol and must never be opened on public networks. If
the active network profile is Public, discovery stays blocked even with these
rules — ``active_profile_is_public`` lets callers warn about that.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

RULE_PROFILES = "private,domain"

# Hide netsh/powershell console windows when called from the windowed exe.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_windows() -> bool:
    return sys.platform == "win32"


@dataclass(frozen=True)
class FirewallRule:
    name: str
    program: Path
    protocol: str  # "TCP" | "UDP"
    localport: str | None = None

    def add_command(self) -> list[str]:
        cmd = [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={self.name}",
            "dir=in",
            "action=allow",
            f"program={self.program}",
            f"protocol={self.protocol}",
            f"profile={RULE_PROFILES}",
        ]
        if self.localport:
            cmd.append(f"localport={self.localport}")
        return cmd

    def delete_command(self) -> list[str]:
        return [
            "netsh", "advfirewall", "firewall", "delete", "rule",
            f"name={self.name}",
        ]


def worker_rules(worker_exe: Path, rpc_exe: Path) -> list[FirewallRule]:
    """The inbound allow rules the worker needs on Windows."""
    return [
        # Node API (8001) + worker launcher control (8090).
        FirewallRule("BSDK Worker (TCP-In)", worker_exe, "TCP"),
        # mDNS announcements/queries — this is what makes auto-discovery work.
        FirewallRule("BSDK Worker (mDNS-In)", worker_exe, "UDP", localport="5353"),
        # GGML RPC (50052) — a separate binary, so it needs its own rule.
        FirewallRule("BSDK GGML RPC (TCP-In)", rpc_exe, "TCP"),
    ]


def rule_exists(name: str) -> bool:
    """True if a rule with this name exists (no elevation required)."""
    if not is_windows():
        return False
    result = subprocess.run(
        ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=_NO_WINDOW,
    )
    return result.returncode == 0


def active_profile_is_public() -> bool:
    """True if the current network is classified as Public.

    On a Public network the private-profile rules do not apply, so discovery
    stays blocked; the user has to mark their (home/office) network as Private
    in Windows Settings.
    """
    if not is_windows():
        return False
    result = subprocess.run(
        ["netsh", "advfirewall", "show", "currentprofile"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        return False
    return "public profile" in (result.stdout or "").lower()


def _run_elevated_batch(commands: list[list[str]]) -> bool:
    """Run netsh commands elevated via one UAC prompt. Returns success."""
    lines = ["@echo off"] + [subprocess.list2cmdline(cmd) for cmd in commands]
    with tempfile.NamedTemporaryFile(
        "w", suffix=".cmd", delete=False, encoding="ascii"
    ) as fh:
        fh.write("\r\n".join(lines) + "\r\n")
        batch = Path(fh.name)
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                f"$p = Start-Process -FilePath '{batch}' -Verb RunAs "
                "-WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120.0,
            creationflags=_NO_WINDOW,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        batch.unlink(missing_ok=True)


def ensure_rules(worker_exe: Path, rpc_exe: Path) -> tuple[bool, str]:
    """Make sure the worker's inbound firewall rules exist. Idempotent."""
    if not is_windows():
        return False, "Firewall rules are Windows-only"

    missing = [r for r in worker_rules(worker_exe, rpc_exe) if not rule_exists(r.name)]
    if not missing:
        return True, "Firewall rules already present"

    # Direct attempt first — succeeds when we are already elevated.
    failed: list[FirewallRule] = []
    for rule in missing:
        result = subprocess.run(
            rule.add_command(), capture_output=True, text=True, check=False,
            creationflags=_NO_WINDOW,
        )
        if result.returncode != 0:
            failed.append(rule)
    if not failed:
        return True, f"Added {len(missing)} firewall rule(s)"

    # Not elevated: one UAC prompt for all remaining rules.
    if _run_elevated_batch([r.add_command() for r in failed]):
        still_missing = [r for r in failed if not rule_exists(r.name)]
        if not still_missing:
            return True, f"Added {len(missing)} firewall rule(s) (elevated)"
    return False, manual_instructions(worker_exe, rpc_exe)


def remove_rules() -> tuple[bool, str]:
    """Best-effort removal of the worker's firewall rules (for uninstall)."""
    if not is_windows():
        return False, "Firewall rules are Windows-only"
    # Rule names are fixed, so we can delete without knowing the install paths.
    names = ["BSDK Worker (TCP-In)", "BSDK Worker (mDNS-In)", "BSDK GGML RPC (TCP-In)"]
    present = [n for n in names if rule_exists(n)]
    if not present:
        return True, "No firewall rules to remove"
    deletes = [
        ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={n}"]
        for n in present
    ]
    failed = False
    for cmd in deletes:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, creationflags=_NO_WINDOW
        )
        if result.returncode != 0:
            failed = True
    if failed and not _run_elevated_batch(deletes):
        return False, "Could not remove firewall rules (elevation declined?)"
    return True, f"Removed {len(present)} firewall rule(s)"


def manual_instructions(worker_exe: Path, rpc_exe: Path) -> str:
    """Commands the user can paste into an elevated prompt themselves."""
    cmds = "\n  ".join(
        subprocess.list2cmdline(r.add_command())
        for r in worker_rules(worker_exe, rpc_exe)
    )
    return (
        "Firewall rules could not be added (auto-discovery will not work "
        "until inbound mDNS/RPC is allowed). Run these in an *Administrator* "
        f"terminal:\n  {cmds}"
    )
