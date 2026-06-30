#!/usr/bin/env python3
"""Compare inference timing with vs. without a worker PC connected.

Workflow:
  1. Start the coordinator WITH the worker PC connected, then run:
       python benchmarks/run_benchmark.py --url http://127.0.0.1:8000 \
           -n 5 --label with-worker -o benchmarks/results/with-worker.json

  2. Stop the node, restart the coordinator WITHOUT the worker (no peer host),
     then run:
       python benchmarks/run_benchmark.py --url http://127.0.0.1:8000 \
           -n 5 --label without-worker -o benchmarks/results/without-worker.json

  3. Compare the two result files:
       python benchmarks/compare_worker.py \
           benchmarks/results/with-worker.json \
           benchmarks/results/without-worker.json

Each result file is the JSON written by run_benchmark.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not read benchmark result {path}: {exc}")
    return data


def _label(data: dict, fallback: str) -> str:
    return str(data.get("label") or fallback)


def _fmt_delta(a: float, b: float, *, lower_is_better: bool, unit: str) -> str:
    """Format the difference between run A and run B (b - a)."""
    diff = b - a
    sign = "+" if diff >= 0 else ""
    note = ""
    if a > 0:
        pct = diff / a * 100
        note = f" ({sign}{pct:.1f}%)"
    if lower_is_better:
        verdict = "faster" if diff < 0 else "slower" if diff > 0 else "same"
    else:
        verdict = "higher" if diff > 0 else "lower" if diff < 0 else "same"
    return f"{sign}{diff:.2f} {unit}{note} [{verdict}]"


def compare(with_worker: dict, without_worker: dict) -> int:
    a_label = _label(with_worker, "with-worker")
    b_label = _label(without_worker, "without-worker")

    rows = [
        ("Total duration", "duration_seconds", "s", True),
        ("Mean latency", "latency_ms_mean", "ms", True),
        ("p50 latency", "latency_ms_p50", "ms", True),
        ("p95 latency", "latency_ms_p95", "ms", True),
        ("Throughput", "tokens_per_second", "tok/s", False),
    ]

    name_w, val_w, diff_w = 18, 15, 30
    total_w = name_w + val_w * 2 + diff_w
    print()
    print(f"Inference timing: {a_label}  vs.  {b_label}")
    print("=" * total_w)
    header = (
        f"{'Metric':<{name_w}}{a_label:>{val_w}}{b_label:>{val_w}}"
        f"{'  Difference (B-A)':<{diff_w}}"
    )
    print(header)
    print("-" * total_w)

    for name, key, unit, lower_is_better in rows:
        a_val = with_worker.get(key)
        b_val = without_worker.get(key)
        if a_val is None or b_val is None:
            print(f"{name:<{name_w}}{'n/a':>{val_w}}{'n/a':>{val_w}}")
            continue
        delta = _fmt_delta(float(a_val), float(b_val), lower_is_better=lower_is_better, unit=unit)
        print(f"{name:<{name_w}}{a_val:>{val_w}.2f}{b_val:>{val_w}.2f}  {delta}")

    print("-" * total_w)

    a_dur = with_worker.get("duration_seconds")
    b_dur = without_worker.get("duration_seconds")
    if a_dur and b_dur:
        diff = b_dur - a_dur
        if diff > 0:
            print(f"\n=> {a_label} was {diff:.2f}s faster overall "
                  f"({b_dur / a_dur:.2f}x) than {b_label}.")
        elif diff < 0:
            print(f"\n=> {b_label} was {-diff:.2f}s faster overall "
                  f"({a_dur / b_dur:.2f}x) than {a_label}.")
        else:
            print("\n=> Both configurations took the same time.")

    a_fail = with_worker.get("failures", 0)
    b_fail = without_worker.get("failures", 0)
    if a_fail or b_fail:
        print(f"\nWarning: failures detected — {a_label}: {a_fail}, {b_label}: {b_fail}")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare two run_benchmark.py result files (worker on vs off)."
    )
    parser.add_argument(
        "with_worker",
        type=Path,
        help="JSON result captured WITH the worker PC connected",
    )
    parser.add_argument(
        "without_worker",
        type=Path,
        help="JSON result captured WITHOUT the worker PC connected",
    )
    args = parser.parse_args()

    return compare(_load(args.with_worker), _load(args.without_worker))


if __name__ == "__main__":
    sys.exit(main())
