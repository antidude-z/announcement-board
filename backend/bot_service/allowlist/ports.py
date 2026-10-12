from typing import Protocol, runtime_checkable

from bot_service.allowlist.dto import AllowlistEntry


@runtime_checkable
class AllowlistRepository(Protocol):
    """Порт хранилища Telegram allowlist внутри bot-service."""

    async def is_allowed(self, telegram_user_id: int) -> bool:
        ...

    async def list_all(self) -> list[AllowlistEntry]:
        ...

    async def add(self, telegram_user_id: int) -> bool:
        ...

    async def remove(self, telegram_user_id: int) -> bool:
        ...

    async def set_username(self, telegram_user_id: int, username: str) -> None:
        ...