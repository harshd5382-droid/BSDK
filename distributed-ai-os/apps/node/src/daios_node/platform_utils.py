"""Cross-platform helpers for the node daemon."""

from __future__ import annotations

import ipaddress
import os
import sys
import threading
import time

import psutil

# psutil.net_connections() enumerates every socket on the machine — an
# expensive syscall (and a slow one on Windows). It is hit from /health,
# /api/v1/cluster, and every gossip heartbeat, all of which are polled on a
# ~2s cadence, so the result is shared for a beat instead of re-scanned per
# caller.
_CONN_TTL = 2.0
_conn_lock = threading.Lock()
_conn_cache: dict[int, tuple[float, int]] = {}


def system_disk_root() -> str:
    """Return the filesystem root for disk-usage reporting."""
    if sys.platform == "win32":
        drive = os.path.splitdrive(os.getcwd())[0]
        return drive + "\\" if drive else "C:\\"
    return os.path.abspath(os.sep)


def count_inbound_tcp_clients(port: int) -> int:
    """Count established inbound TCP connections to a local port (non-loopback peers).

    Cached for ``_CONN_TTL`` seconds — see the note above.
    """
    now = time.monotonic()
    with _conn_lock:
        cached = _conn_cache.get(port)
        if cached is not None and now - cached[0] < _CONN_TTL:
            return cached[1]

    total = _scan_inbound_tcp_clients(port)
    with _conn_lock:
        _conn_cache[port] = (time.monotonic(), total)
    return total


def _scan_inbound_tcp_clients(port: int) -> int:
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
