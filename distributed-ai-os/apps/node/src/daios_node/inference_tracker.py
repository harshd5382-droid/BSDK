"""Track in-flight OpenAI-compatible inference requests on the coordinator."""

from __future__ import annotations

import threading


class InferenceTracker:
    """Thread-safe counter for active /v1 inference requests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    def begin(self) -> None:
        with self._lock:
            self._active += 1

    def end(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
