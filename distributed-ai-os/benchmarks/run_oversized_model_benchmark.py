#!/usr/bin/env python3
"""Oversized-model memory-pooling benchmark.

Skips if no model exceeding single-node RAM is available.
Expects single-node OOM and distributed success when model is too large for one node.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results" / "gen1-oversized-model.json"
MODELS_DIR = ROOT / "models"


def _model_size_gb(path: Path) -> float:
    return path.stat().st_size / (1024**3)


def _find_oversized_model(threshold_gb: float) -> Path | None:
    if not MODELS_DIR.is_dir():
        return None
    for gguf in sorted(MODELS_DIR.glob("*.gguf")):
        if _model_size_gb(gguf) > threshold_gb:
            return gguf
    return None


def main() -> int:
    ram_gb = psutil.virtual_memory().total / (1024**3)
    threshold = ram_gb * 0.8  # model must exceed ~80% of RAM to force pooling
    model = _find_oversized_model(threshold)

    if model is None:
        print(f"SKIP: No GGUF model in {MODELS_DIR} exceeds {threshold:.1f} GB (RAM={ram_gb:.1f} GB).")
        print("Place a model larger than single-node RAM in models/ and re-run.")
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(
            json.dumps(
                {
                    "status": "deferred",
                    "reason": "no_oversized_model",
                    "ram_gb": round(ram_gb, 2),
                    "threshold_gb": round(threshold, 2),
                },
                indent=2,
            )
        )
        return 0

    print(f"Found oversized model: {model.name} ({_model_size_gb(model):.2f} GB)")
    print("Manual steps:")
    print("  1. Start worker on machine B: daios-node -c examples/two-node/worker.yaml")
    print("  2. Configure coordinator with model_path pointing to this model")
    print("  3. Verify single-node fails with OOM, distributed succeeds")
    print(f"  4. Record results in {RESULTS}")

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(
        json.dumps(
            {
                "status": "ready",
                "model": str(model),
                "model_size_gb": round(_model_size_gb(model), 2),
                "ram_gb": round(ram_gb, 2),
                "instructions": "Run distributed inference and record throughput/latency",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
