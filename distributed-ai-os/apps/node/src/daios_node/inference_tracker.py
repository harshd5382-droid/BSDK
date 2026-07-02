"""Track in-flight and cumulative OpenAI-compatible inference requests."""

from __future__ import annotations

import threading
import time


class InferenceTracker:
    """Thread-safe counters for active + cumulative /v1 inference requests.

    Records request counts, failures, latency, and (best-effort) generated tokens
    so the coordinator can expose real throughput/latency metrics.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._total = 0
        self._failures = 0
        self._total_latency_s = 0.0
        self._last_latency_ms = 0.0
        self._total_tokens = 0

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    def begin(self) -> float:
        """Mark a request started; returns a start timestamp to pass to ``end``."""
        with self._lock:
            self._active += 1
        return time.monotonic()

    def end(self, start: float | None = None, *, tokens: int = 0, failed: bool = False) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
            self._total += 1
            if failed:
                self._failures += 1
            if start is not None:
                duration = max(0.0, time.monotonic() - start)
                self._total_latency_s += duration
                self._last_latency_ms = duration * 1000.0
            if tokens > 0:
                self._total_tokens += tokens

    def snapshot(self) -> dict:
        with self._lock:
            completed = self._total
            avg_latency_ms = (self._total_latency_s / completed * 1000.0) if completed else 0.0
            tokens_per_second = (
                self._total_tokens / self._total_latency_s if self._total_latency_s > 0 else 0.0
            )
            return {
                "active_requests": self._active,
                "total_requests": self._total,
                "failed_requests": self._failures,
                "avg_latency_ms": round(avg_latency_ms, 1),
                "last_latency_ms": round(self._last_latency_ms, 1),
                "total_tokens": self._total_tokens,
                "tokens_per_second": round(tokens_per_second, 2),
            }
