"""Cross-platform helpers for the node daemon."""

from __future__ import annotations

import ipaddress
import os
import sys

import psutil


def system_disk_root() -> str:
    """Return the filesystem root for disk-usage reporting."""
    if sys.platform == "win32":
        drive = os.path.splitdrive(os.getcwd())[0]
        return drive + "\\" if drive else "C:\\"
    return os.path.abspath(os.sep)


def count_inbound_tcp_clients(port: int) -> int:
    """Count established inbound TCP connections to a local port (non-loopback peers)."""
    total = 0
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_ESTABLISHED:
                continue
            if not conn.laddr or conn.laddr.port != port:
                continue
            if not conn.raddr:
                continue
            try:
                addr = ipaddress.ip_address(conn.raddr.ip)
                if addr.is_loopback:
                    continue
            except ValueError:
                continue
            total += 1
    except (psutil.AccessDenied, psutil.Error):
        return 0
    return total
