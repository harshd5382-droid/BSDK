"""Read model context length from GGUF metadata."""

from __future__ import annotations

import mmap
import struct
from pathlib import Path

GGUF_MAGIC = 0x46554747  # "GGUF" as little-endian uint32

# gguf_metadata_value_type
_TYPE_UINT8 = 0
_TYPE_INT8 = 1
_TYPE_UINT16 = 2
_TYPE_INT16 = 3
_TYPE_UINT32 = 4
_TYPE_INT32 = 5
_TYPE_FLOAT32 = 6
_TYPE_BOOL = 7
_TYPE_STRING = 8
_TYPE_ARRAY = 9
_TYPE_UINT64 = 10
_TYPE_INT64 = 11
_TYPE_FLOAT64 = 12


def _read_string(data: bytes, offset: int) -> tuple[str, int]:
    (length,) = struct.unpack_from("<Q", data, offset)
    offset += 8
    text = data[offset : offset + length].decode("utf-8")
    return text, offset + length


def _skip_value(data: bytes, offset: int, value_type: int) -> int:
    if value_type == _TYPE_UINT8:
        return offset + 1
    if value_type == _TYPE_INT8:
        return offset + 1
    if value_type in (_TYPE_UINT16, _TYPE_INT16):
        return offset + 2
    if value_type in (_TYPE_UINT32, _TYPE_INT32, _TYPE_FLOAT32):
        return offset + 4
    if value_type == _TYPE_BOOL:
        return offset + 1
    if value_type == _TYPE_STRING:
        _, offset = _read_string(data, offset)
        return offset
    if value_type in (_TYPE_UINT64, _TYPE_INT64, _TYPE_FLOAT64):
        return offset + 8
    if value_type == _TYPE_ARRAY:
        (item_type,) = struct.unpack_from("<I", data, offset)
        offset += 4
        (count,) = struct.unpack_from("<Q", data, offset)
        offset += 8
        for _ in range(count):
            offset = _skip_value(data, offset, item_type)
        return offset
    raise ValueError(f"unsupported GGUF value type: {value_type}")


def _read_scalar(data: bytes, offset: int, value_type: int) -> tuple[object, int]:
    if value_type == _TYPE_UINT8:
        return struct.unpack_from("<B", data, offset)[0], offset + 1
    if value_type == _TYPE_INT8:
        return struct.unpack_from("<b", data, offset)[0], offset + 1
    if value_type == _TYPE_UINT16:
        return struct.unpack_from("<H", data, offset)[0], offset + 2
    if value_type == _TYPE_INT16:
        return struct.unpack_from("<h", data, offset)[0], offset + 2
    if value_type == _TYPE_UINT32:
        return struct.unpack_from("<I", data, offset)[0], offset + 4
    if value_type == _TYPE_INT32:
        return struct.unpack_from("<i", data, offset)[0], offset + 4
    if value_type == _TYPE_FLOAT32:
        return struct.unpack_from("<f", data, offset)[0], offset + 4
    if value_type == _TYPE_BOOL:
        return bool(struct.unpack_from("<B", data, offset)[0]), offset + 1
    if value_type == _TYPE_STRING:
        return _read_string(data, offset)
    if value_type == _TYPE_UINT64:
        return struct.unpack_from("<Q", data, offset)[0], offset + 8
    if value_type == _TYPE_INT64:
        return struct.unpack_from("<q", data, offset)[0], offset + 8
    if value_type == _TYPE_FLOAT64:
        return struct.unpack_from("<d", data, offset)[0], offset + 8
    if value_type == _TYPE_ARRAY:
        offset = _skip_value(data, offset, value_type)
        return None, offset
    raise ValueError(f"unsupported GGUF value type: {value_type}")


def read_gguf_metadata(path: Path) -> dict[str, object]:
    """Return scalar metadata key/value pairs from a GGUF file header.

    The metadata block lives at the very start of the file, before the tensor
    data. We memory-map the file (read-only) so only the header pages actually
    touched are paged into RAM. This avoids loading a multi-GB model fully into
    memory just to parse a few kilobytes of header, which previously caused
    swap thrashing / full-system freezes on large models.
    """
    with path.open("rb") as fh:
        size = path.stat().st_size
        if size < 24:
            raise ValueError("file too small for GGUF header")

        with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
            (magic, version, _tensor_count, kv_count) = struct.unpack_from("<IIQQ", data, 0)
            if magic != GGUF_MAGIC:
                raise ValueError("not a GGUF file")
            if version not in (2, 3):
                raise ValueError(f"unsupported GGUF version: {version}")

            offset = 24
            metadata: dict[str, object] = {}
            for _ in range(kv_count):
                key, offset = _read_string(data, offset)
                (value_type,) = struct.unpack_from("<I", data, offset)
                offset += 4
                value, offset = _read_scalar(data, offset, value_type)
                if value is not None:
                    metadata[key] = value
            return metadata


def estimate_kv_bytes_per_token(model_path: str | Path) -> int | None:
    """Bytes of KV cache one token costs for this model, or None if unknown.

    The KV cache is a hard up-front allocation sized by the context window, and
    for a long-context model it dwarfs the weights: Qwen2.5-14B needs ~192 KiB
    per token, so its declared 128k context asks for ~24 GB before a single
    token is generated. Callers use this to pick a context the machine can
    actually allocate instead of trusting the model's advertised maximum.

    Assumes f16 K and V entries (llama.cpp's default cache type).
    """
    path = Path(model_path)
    if not path.is_file():
        return None
    try:
        metadata = read_gguf_metadata(path)
    except (OSError, ValueError, struct.error, UnicodeDecodeError):
        return None

    arch = metadata.get("general.architecture")
    if not isinstance(arch, str):
        return None

    def _int(key: str) -> int | None:
        value = metadata.get(f"{arch}.{key}")
        return value if isinstance(value, int) and value > 0 else None

    layers = _int("block_count")
    kv_heads = _int("attention.head_count_kv") or _int("attention.head_count")
    if not layers or not kv_heads:
        return None

    head_dim = _int("attention.key_length")
    if head_dim is None:
        embedding = _int("embedding_length")
        heads = _int("attention.head_count")
        if not embedding or not heads:
            return None
        head_dim = embedding // heads
    if head_dim <= 0:
        return None

    # K and V, f16 (2 bytes per element).
    return 2 * layers * kv_heads * head_dim * 2


def infer_context_size(model_path: str | Path) -> int | None:
    """Return the model's trained context length from GGUF metadata, if present."""
    path = Path(model_path)
    if not path.is_file():
        return None

    try:
        metadata = read_gguf_metadata(path)
    except (OSError, ValueError, struct.error, UnicodeDecodeError):
        return None

    arch = metadata.get("general.architecture")
    if isinstance(arch, str):
        key = f"{arch}.context_length"
        value = metadata.get(key)
        if isinstance(value, int) and value > 0:
            return value

    for key, value in metadata.items():
        if key.endswith(".context_length") and isinstance(value, int) and value > 0:
            return value

    return None
