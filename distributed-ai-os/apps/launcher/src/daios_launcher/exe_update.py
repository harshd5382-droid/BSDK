"""Push-based exe update: distribute a new daios-worker.exe from the coordinator.

The coordinator (main PC) serves its freshly built ``dist/daios-worker.exe`` over
the launcher API (token-protected off-loopback). When the user clicks Update in
the dashboard, the worker downloads the exe from the coordinator, verifies the
SHA-256 the coordinator announced, stages it, and relaunches through the
installer's own idempotent update flow (stop service → swap exe atomically →
restart service → re-register autostart). A failed download or checksum leaves
the running install untouched.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from daios_launcher import paths
from daios_launcher.artifacts import DownloadError, sha256_file, verify_sha256

logger = logging.getLogger(__name__)

STAGED_EXE_NAME = "daios-worker-update.exe"

# sha256 of a ~30 MB exe takes noticeable time; cache keyed by (path, size, mtime).
_info_cache: dict[tuple[str, int, float], dict] = {}


def serveable_worker_exe(project_root: Path) -> Path | None:
    """The worker exe this launcher can distribute to other PCs, if any.

    Frozen (a worker updating a worker is not a supported topology, but a frozen
    coordinator/hybrid can still re-serve itself): the running exe. From source
    (the usual main-PC case): the local PyInstaller build in ``dist/``.
    """
    if paths.is_frozen():
        return Path(sys.executable)
    candidate = project_root / "dist" / "daios-worker.exe"
    if candidate.is_file() and candidate.stat().st_size > 0:
        return candidate
    return None


def exe_info(path: Path) -> dict:
    """{sha256, size_bytes, modified} for an exe, cached across calls."""
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime)
    cached = _info_cache.get(key)
    if cached is None:
        cached = {
            "sha256": sha256_file(path),
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
        _info_cache.clear()  # only ever a handful of entries; keep it tiny
        _info_cache[key] = cached
    return cached


def current_exe_sha256() -> str | None:
    """SHA-256 of the running exe (frozen installs only)."""
    if not paths.is_frozen():
        return None
    return exe_info(Path(sys.executable))["sha256"]


def download_worker_exe(
    source_host: str,
    source_port: int,
    expected_sha256: str,
    token: str | None,
    *,
    downloader: Callable[[str, Path], None] | None = None,
) -> Path:
    """Download the coordinator's exe into staging and verify it. Returns the path.

    Raises :class:`daios_launcher.artifacts.ArtifactError` on failure; the
    caller must treat that as "no update happened" — the install is untouched.
    """
    url = f"http://{source_host}:{source_port}/api/launcher/worker-exe"
    staging = paths.staging_dir()
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / STAGED_EXE_NAME
    staged.unlink(missing_ok=True)

    if downloader is None:

        def downloader(dl_url: str, dest: Path) -> None:
            import httpx

            headers = {"X-DAIOS-Token": token} if token else {}
            try:
                with httpx.stream(
                    "GET", dl_url, headers=headers, follow_redirects=True, timeout=300.0
                ) as resp:
                    resp.raise_for_status()
                    with dest.open("wb") as fh:
                        for chunk in resp.iter_bytes(chunk_size=1 << 20):
                            fh.write(chunk)
            except httpx.HTTPError as exc:
                raise DownloadError(f"Download failed for {dl_url}: {exc}") from exc

    logger.info("Downloading worker exe update from %s", url)
    downloader(url, staged)
    if not staged.is_file() or staged.stat().st_size == 0:
        raise DownloadError("Downloaded exe is empty")
    # Verify BEFORE launching anything: a bad download never replaces the install.
    verify_sha256(staged, expected_sha256)
    logger.info("Exe update checksum OK: %s", staged)
    return staged


def spawn_staged_installer(staged_exe: Path) -> subprocess.Popen:
    """Run the staged exe in install mode, detached from this (doomed) process.

    Install mode stops the running worker service (us), swaps the installed exe
    atomically, refreshes the autostart task, and restarts the service.
    """
    log_path = paths.logs_dir() / "worker-update.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    log_handle = open(log_path, "ab")
    return subprocess.Popen(
        [str(staged_exe)],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )
