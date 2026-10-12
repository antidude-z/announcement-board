from datetime import datetime, timezone

from auth.tokens import encode_session_token


class SessionRegistry:
    """In-memory реестр активных сессий (jti -> exp). Redis-адаптер — отдельный шаг."""

    def __init__(self):
        self._active: dict[str, datetime] = {}

    def register(self, jti: str, expires_at: datetime) -> None:
        self._prune()
        self._active[jti] = expires_at

    def is_active(self, jti: str) -> bool:
        self._prune()
        return jti in self._active

    def revoke(self, jti: str) -> None:
        self._active.pop(jti, None)

    def _prune(self) -> None:
        now = datetime.now(timezone.utc)
        self._active = {jti: exp for jti, exp in self._active.items() if exp > now}


SESSION_REGISTRY = SessionRegistry()


def create_session_token(role: str, subject: str) -> str:
    token, jti, expires_at = encode_session_token(role, subject)
    SESSION_REGISTRY.register(jti, expires_at)
    return token