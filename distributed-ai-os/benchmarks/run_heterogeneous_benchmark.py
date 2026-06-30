#!/usr/bin/env python3
"""CPU+GPU heterogeneous benchmark via GGML RPC tensor split.

Skips automatically if no NVIDIA GPU is detected.
Writes results to benchmarks/results/gen1-heterogeneous.json
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results" / "gen1-heterogeneous.json"


def has_nvidia_gpu() -> bool:
    return shutil.which("nvidia-smi") is not None


def main() -> int:
    if not has_nvidia_gpu():
        print("SKIP: No NVIDIA GPU detected (nvidia-smi not found).")
        print("Run on a machine with GPU to collect heterogeneous benchmark.")
        return 0

    print("GPU detected. Run coordinator with tensor_split for CPU+GPU split.")
    print("Example config snippet:")
    print('  inference:')
    print('    n_gpu_layers: 20')
    print('    tensor_split: "0.5,0.5"  # adjust for your topology')
    print()
    print("Then run: make benchmark")
    print(f"Copy results manually to {RESULTS}")

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    stub = {
        "status": "deferred",
        "reason": "Requires manual tensor_split configuration per hardware",
        "gpu_detected": True,
        "instructions": "Configure tensor_split in coordinator YAML and run make benchmark",
    }
    RESULTS.write_text(json.dumps(stub, indent=2))
    print(f"Wrote stub status to {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
