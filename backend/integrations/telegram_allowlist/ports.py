from typing import Protocol, runtime_checkable

from integrations.telegram_allowlist.dto import TelegramAllowlistEntry


@runtime_checkable
class TelegramAllowlistGateway(Protocol):
    """Порт для управления Telegram allowlist из backend."""

    async def list_all(self) -> list[TelegramAllowlistEntry]:
        ...

    async def add(self, telegram_user_id: int) -> bool:
        ...

    async def remove(self, telegram_user_id: int) -> bool:
        ...