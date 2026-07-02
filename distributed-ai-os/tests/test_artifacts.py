"""Tests for secure binary acquisition (download + SHA-256 verify)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from daios_launcher import artifacts


def _make_archive(path: Path, *, include_rpc: bool = True) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        if include_rpc:
            zf.writestr("ggml-rpc-server.exe", b"MZ fake rpc server binary")
        zf.writestr("ggml.dll", b"fake dll")
    return path


def _manifest(url: str, sha: str) -> artifacts.BinaryManifest:
    return artifacts.BinaryManifest(archive_url=url, archive_sha256=sha)


def test_verify_sha256_pass_and_fail(tmp_path):
    f = tmp_path / "blob.bin"
    f.write_bytes(b"hello world")
    good = artifacts.sha256_file(f)
    artifacts.verify_sha256(f, good)  # no raise
    with pytest.raises(artifacts.ChecksumError):
        artifacts.verify_sha256(f, "0" * 64)


def test_already_present_is_reused(tmp_path):
    dest = tmp_path / "bin"
    dest.mkdir()
    rpc = dest / "ggml-rpc-server.exe"
    rpc.write_bytes(b"already here")
    manifest = _manifest("http://example/none.zip", artifacts.UNPUBLISHED_SHA)
    result = artifacts.ensure_worker_binaries(manifest, dest)
    assert result == rpc


def test_missing_binary_when_unpublished_and_no_bundle(tmp_path):
    dest = tmp_path / "bin"
    manifest = _manifest("http://example/none.zip", artifacts.UNPUBLISHED_SHA)
    with pytest.raises(artifacts.MissingBinaryError):
        artifacts.ensure_worker_binaries(manifest, dest)


def test_download_and_verify_success(tmp_path):
    archive = _make_archive(tmp_path / "src.zip")
    sha = artifacts.sha256_file(archive)
    dest = tmp_path / "install bin with spaces"  # path containing spaces

    def fake_download(url: str, out: Path) -> None:
        out.write_bytes(archive.read_bytes())

    manifest = _manifest("http://example/worker.zip", sha)
    rpc = artifacts.ensure_worker_binaries(manifest, dest, downloader=fake_download)
    assert rpc.is_file()
    assert (dest / "ggml.dll").is_file()  # DLLs flattened in too


def test_checksum_failure_does_not_corrupt_dest(tmp_path):
    archive = _make_archive(tmp_path / "src.zip")
    dest = tmp_path / "bin"
    dest.mkdir()
    (dest / "ggml-rpc-server.exe").write_bytes(b"")  # empty -> not "present"
    # Empty file => treated as absent, so it will try to download with a wrong sha.
    (dest / "ggml-rpc-server.exe").unlink()

    def fake_download(url: str, out: Path) -> None:
        out.write_bytes(archive.read_bytes())

    manifest = _manifest("http://example/worker.zip", "0" * 64)
    with pytest.raises(artifacts.ChecksumError):
        artifacts.ensure_worker_binaries(manifest, dest, downloader=fake_download)
    # Nothing was committed into dest.
    assert not (dest / "ggml-rpc-server.exe").exists()


def test_corrupt_archive_missing_rpc(tmp_path):
    archive = _make_archive(tmp_path / "src.zip", include_rpc=False)
    sha = artifacts.sha256_file(archive)
    dest = tmp_path / "bin"

    def fake_download(url: str, out: Path) -> None:
        out.write_bytes(archive.read_bytes())

    manifest = _manifest("http://example/worker.zip", sha)
    with pytest.raises(artifacts.MissingBinaryError):
        artifacts.ensure_worker_binaries(manifest, dest, downloader=fake_download)


def test_bundled_binaries_are_used(tmp_path):
    bundled = tmp_path / "meipass" / "bin"
    bundled.mkdir(parents=True)
    (bundled / "ggml-rpc-server.exe").write_bytes(b"bundled rpc")
    (bundled / "ggml.dll").write_bytes(b"bundled dll")
    dest = tmp_path / "install"
    manifest = _manifest("http://example/none.zip", artifacts.UNPUBLISHED_SHA)
    rpc = artifacts.ensure_worker_binaries(manifest, dest, bundled_bin=bundled)
    assert rpc.is_file()
    assert (dest / "ggml.dll").is_file()
