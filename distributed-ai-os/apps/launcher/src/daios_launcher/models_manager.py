"""Coordinator model download and selection."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass
class DownloadState:
    status: str = "idle"  # idle | downloading | complete | error
    filename: str | None = None
    bytes_done: int = 0
    bytes_total: int | None = None
    error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "filename": self.filename,
                "bytes_done": self.bytes_done,
                "bytes_total": self.bytes_total,
                "error": self.error,
                "percent": (
                    round(self.bytes_done / self.bytes_total * 100, 1)
                    if self.bytes_total and self.bytes_total > 0
                    else None
                ),
            }

    def reset(self) -> None:
        with self._lock:
            self.status = "idle"
            self.filename = None
            self.bytes_done = 0
            self.bytes_total = None
            self.error = None


download_state = DownloadState()


def list_models(models_dir: Path, active: str | None = None) -> list[dict]:
    if not models_dir.is_dir():
        return []
    result = []
    for path in sorted(models_dir.glob("*.gguf")):
        stat = path.stat()
        result.append(
            {
                "name": path.name,
                "path": str(path),
                "size_gb": round(stat.st_size / (1024**3), 2),
                "active": path.name == active,
            }
        )
    return result


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", name.strip())
    if not cleaned.endswith(".gguf"):
        cleaned = f"{cleaned}.gguf"
    return cleaned


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name or "model.gguf"
    return _safe_filename(name)


def download_model(
    project_root: Path,
    *,
    url: str | None = None,
    hf_repo: str | None = None,
    filename: str | None = None,
) -> None:
    """Background download into ``models/``."""
    models_dir = project_root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    with download_state._lock:
        if download_state.status == "downloading":
            download_state.error = "Download already in progress"
            download_state.status = "error"
            return
        download_state.status = "downloading"
        download_state.bytes_done = 0
        download_state.bytes_total = None
        download_state.error = None

    try:
        if hf_repo:
            dest_name = _safe_filename(filename or f"{hf_repo.replace('/', '_')}.gguf")
            dest = models_dir / dest_name
            with download_state._lock:
                download_state.filename = dest_name
            _download_hf(hf_repo, dest)
        elif url:
            dest_name = _safe_filename(filename or _filename_from_url(url))
            dest = models_dir / dest_name
            with download_state._lock:
                download_state.filename = dest_name
            _download_url(url, dest)
        else:
            raise ValueError("Provide url or hf_repo")
        with download_state._lock:
            download_state.status = "complete"
    except Exception as exc:
        logger.exception("Model download failed")
        with download_state._lock:
            download_state.status = "error"
            download_state.error = str(exc)


def _download_url(url: str, dest: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=600.0) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0)) or None
        with download_state._lock:
            download_state.bytes_total = total
        with dest.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                fh.write(chunk)
                with download_state._lock:
                    download_state.bytes_done += len(chunk)


def _download_hf(repo: str, dest: Path) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub not installed") from exc

    parts = repo.split(":")
    repo_id = parts[0]
    file_name = parts[1] if len(parts) > 1 else None
    if not file_name:
        raise ValueError("hf_repo must be 'org/model:filename.gguf'")

    with download_state._lock:
        download_state.bytes_total = None

    path = hf_hub_download(repo_id=repo_id, filename=file_name, local_dir=str(dest.parent))
    downloaded = Path(path)
    if downloaded != dest:
        downloaded.replace(dest)
    with download_state._lock:
        download_state.bytes_done = dest.stat().st_size
        download_state.bytes_total = dest.stat().st_size


def delete_model(models_dir: Path, name: str) -> None:
    safe = _safe_filename(name)
    path = models_dir / safe
    if not path.is_file():
        raise FileNotFoundError(name)
    path.unlink()
