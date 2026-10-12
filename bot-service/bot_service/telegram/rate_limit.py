import time


class TgRateLimiter:
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._cache: dict[int, list[float]] = {}

    def is_limited(self, telegram_user_id: int) -> bool:
        now = time.monotonic()

        entries = [
            ts
            for ts in self._cache.get(telegram_user_id, [])
            if now - ts < self._window_seconds
        ]

        if len(entries) >= self._max_requests:
            self._cache[telegram_user_id] = entries
            return True

        entries.append(now)
        self._cache[telegram_user_id] = entries
        return False