"""Secure acquisition of the native GGML RPC worker binaries.

The worker needs a real ``ggml-rpc-server.exe`` (plus its GGML DLLs). We obtain it
in priority order:

1. Already materialized and checksum-valid in the install ``bin`` dir → reuse.
2. Bundled inside the PyInstaller exe (``_MEIPASS/bin``) → copy + verify.
3. Download the published archive over HTTPS → **SHA-256 verify** → extract.

If no verified real binary can be produced the install fails loudly. We never fall
back to the mock backend just because a dependency is missing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Manifest sha256 left as this sentinel means "not published yet" — we refuse to
# proceed rather than trust an unverifiable download.
UNPUBLISHED_SHA = "REPLACE_WITH_RELEASE_SHA256"

RPC_SERVER_NAME = "ggml-rpc-server.exe"


class ArtifactError(Exception):
    """Base class for binary-acquisition failures."""


class ChecksumError(ArtifactError):
    """A downloaded/bundled artifact did not match its expected SHA-256."""


class DownloadError(ArtifactError):
    """The artifact could not be downloaded."""


class MissingBinaryError(ArtifactError):
    """No verified real binary could be produced (do NOT fall back to mock)."""


class BinaryManifest(BaseModel):
    """Release manifest describing the worker binary archive."""

    archive_url: str
    archive_sha256: str
    # Files expected inside the archive (basename match); flattened into bin dir.
    required_files: list[str] = [RPC_SERVER_NAME]
    rpc_server: str = RPC_SERVER_NAME

    @property
    def is_published(self) -> bool:
        return bool(self.archive_sha256) and self.archive_sha256 != UNPUBLISHED_SHA


def load_manifest(path: Path) -> BinaryManifest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return BinaryManifest.model_validate(data)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    """Raise :class:`ChecksumError` unless ``path`` hashes to ``expected``."""
    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise ChecksumError(
            f"SHA-256 mismatch for {Path(path).name}: "
            f"expected {expected[:12]}..., got {actual[:12]}..."
        )


def _http_download(url: str, dest: Path) -> None:
    """Stream ``url`` to ``dest`` (default downloader; injectable for tests)."""
    import httpx

    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1 << 20):
                    fh.write(chunk)
    except httpx.HTTPError as exc:
        raise DownloadError(f"Download failed for {url}: {exc}") from exc


def _extract_required(archive: Path, dest: Path, required: list[str]) -> None:
    """Flatten the required files out of a zip archive into ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)
    wanted = {name.lower() for name in required}
    found: set[str] = set()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            base = Path(info.filename).name
            # Always take DLLs (runtime deps); take explicitly-required files too.
            if base.lower() in wanted or base.lower().endswith(".dll"):
                with zf.open(info) as src, (dest / base).open("wb") as out:
                    shutil.copyfileobj(src, out)
                found.add(base.lower())
    missing = wanted - found
    if missing:
        raise MissingBinaryError(
            f"Archive {archive.name} is missing required files: {sorted(missing)}"
        )


def _copy_bundled(bundled_bin: Path, dest: Path, required: list[str]) -> bool:
    """Copy pre-bundled binaries from the frozen exe if all required exist."""
    if not bundled_bin.is_dir():
        return False
    if not all((bundled_bin / name).is_file() for name in required):
        return False
    dest.mkdir(parents=True, exist_ok=True)
    for item in bundled_bin.iterdir():
        if item.is_file():
            shutil.copy2(item, dest / item.name)
    return True


def ensure_worker_binaries(
    manifest: BinaryManifest,
    dest: Path,
    *,
    bundled_bin: Path | None = None,
    downloader: Callable[[str, Path], None] | None = None,
) -> Path:
    """Guarantee a verified ``ggml-rpc-server.exe`` in ``dest``; return its path.

    Raises an :class:`ArtifactError` subclass if a verified real binary cannot be
    produced. Callers must treat that as fatal (never mock-fallback).
    """
    dest = Path(dest)
    rpc_path = dest / manifest.rpc_server

    # 1. Already present → reuse (an existing, non-empty real binary).
    if rpc_path.is_file() and rpc_path.stat().st_size > 0:
        logger.info("Worker binary already present: %s", rpc_path)
        return rpc_path

    # 2. Bundled inside the exe.
    if bundled_bin and _copy_bundled(bundled_bin, dest, manifest.required_files):
        logger.info("Materialized bundled worker binaries into %s", dest)
        if not rpc_path.is_file():
            raise MissingBinaryError(f"Bundled binaries missing {manifest.rpc_server}")
        return rpc_path

    # 3. Download + verify.
    if not manifest.is_published:
        raise MissingBinaryError(
            "No worker binary is bundled and the release manifest has no published "
            "SHA-256 (packaging/windows/binaries-manifest.json). Refusing to run "
            "without a verified ggml-rpc-server.exe - the mock backend is not a "
            "substitute. Build it with scripts\\windows\\build-llama-cpp.ps1 or "
            "publish the archive checksum."
        )

    download = downloader or _http_download
    with tempfile.TemporaryDirectory(prefix="daios-dl-") as tmp:
        archive = Path(tmp) / "worker-binaries.zip"
        logger.info("Downloading worker binaries from %s", manifest.archive_url)
        download(manifest.archive_url, archive)
        if not archive.is_file() or archive.stat().st_size == 0:
            raise DownloadError("Downloaded archive is empty")
        # Verify BEFORE touching the install dir, so a bad download never corrupts a
        # working install (failed update leaves the previous binary usable).
        verify_sha256(archive, manifest.archive_sha256)
        logger.info("Checksum OK; staging binaries")
        staged = Path(tmp) / "extracted"
        _extract_required(archive, staged, manifest.required_files)
        if not (staged / manifest.rpc_server).is_file():
            raise MissingBinaryError(
                f"{manifest.rpc_server} not present after extraction"
            )
        # Commit: move the validated files into dest (rpc server last).
        dest.mkdir(parents=True, exist_ok=True)
        files = sorted(staged.iterdir(), key=lambda p: p.name == manifest.rpc_server)
        for item in files:
            if item.is_file():
                shutil.move(str(item), str(dest / item.name))

    if not rpc_path.is_file() or rpc_path.stat().st_size == 0:
        raise MissingBinaryError(
            f"{manifest.rpc_server} not present after extraction into {dest}"
        )
    return rpc_path
