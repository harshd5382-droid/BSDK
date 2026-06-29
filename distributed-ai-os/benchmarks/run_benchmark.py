#!/usr/bin/env python3
"""Generation 1 benchmark suite for distributed inference validation."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx


@dataclass
class BenchmarkResult:
    name: str
    requests: int
    success: int
    failures: int
    latency_ms_p50: float
    latency_ms_p95: float
    latency_ms_mean: float
    tokens_per_second: float | None
    duration_seconds: float


def run_chat_benchmark(
    base_url: str,
    requests: int,
    prompt: str,
    max_tokens: int = 64,
    model: str = "daios",
) -> BenchmarkResult:
    latencies: list[float] = []
    tokens: list[int] = []
    completion_tokens: list[int] = []
    failures = 0
    start = time.perf_counter()

    with httpx.Client(timeout=300.0) as client:
        for i in range(requests):
            t0 = time.perf_counter()
            try:
                response = client.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "user", "content": f"{prompt} (request {i + 1})"}
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.7,
                    },
                )
                response.raise_for_status()
                data = response.json()
                latencies.append((time.perf_counter() - t0) * 1000)
                usage = data.get("usage", {})
                tokens.append(usage.get("total_tokens", 0))
                completion_tokens.append(usage.get("completion_tokens", 0))
            except httpx.HTTPError:
                failures += 1

    duration = time.perf_counter() - start
    success = len(latencies)
    total_completion = sum(completion_tokens)
    # Generation throughput: completion tokens produced per wall-clock second.
    tps = total_completion / duration if duration > 0 else None

    return BenchmarkResult(
        name="chat_completions",
        requests=requests,
        success=success,
        failures=failures,
        latency_ms_p50=statistics.median(latencies) if latencies else 0.0,
        latency_ms_p95=(
            sorted(latencies)[min(int(len(latencies) * 0.95), len(latencies) - 1)]
            if latencies
            else 0.0
        ),
        latency_ms_mean=statistics.mean(latencies) if latencies else 0.0,
        tokens_per_second=tps,
        duration_seconds=duration,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="DAIOS Generation 1 benchmarks")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="Coordinator API base URL",
    )
    parser.add_argument("-n", "--requests", type=int, default=10)
    parser.add_argument("-m", "--max-tokens", type=int, default=64)
    parser.add_argument("--label", default="", help="Label stored in results")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write JSON results to file",
    )
    args = parser.parse_args()

    print(f"Benchmarking {args.url} ({args.requests} requests, max_tokens={args.max_tokens})...")
    result = run_chat_benchmark(
        args.url,
        args.requests,
        "Explain one benefit of distributed systems",
        max_tokens=args.max_tokens,
    )
    payload = asdict(result)
    if args.label:
        payload["label"] = args.label
    print(json.dumps(payload, indent=2))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n")

    return 0 if result.failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
