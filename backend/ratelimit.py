"""Sliding-window rate limiter (in-memory; Redis-адаптер — отдельный шаг)."""
import time


class InMemoryRateLimiter:
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}

    def is_limited(self, key: str) -> bool:
        now = time.monotonic()
        hits = [t for t in self._hits.get(key, []) if now - t < self._window_seconds]

        if len(hits) >= self._max_requests:
            self._hits[key] = hits
            return True

        hits.append(now)
        self._hits[key] = hits
        return False