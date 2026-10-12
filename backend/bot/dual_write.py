import logging

from ports import AllowlistEntry, AllowlistStore

logger = logging.getLogger("legacy-backend.bot.dualwrite")


class DualWriteAllowlistStore:
    """Шаг 3 миграции: dual-write для telegram_allowlist.

    Читает из read_store, пишет в read_store и mirror_store.
    Обе копии остаются свежими, пока dual-write не отрезан (шаг 5).
    Ошибка записи в mirror намеренно не глотается: устаревшая копия
    для отката хуже честной ошибки.
    """

    def __init__(self, read_store: AllowlistStore, mirror_store: AllowlistStore):
        self._read = read_store
        self._mirror = mirror_store

    async def is_allowed(self, telegram_user_id: int) -> bool:
        return await self._read.is_allowed(telegram_user_id)

    async def list_all(self) -> list[AllowlistEntry]:
        return await self._read.list_all()

    async def add(self, telegram_user_id: int) -> bool:
        created = await self._read.add(telegram_user_id)
        await self._mirror.add(telegram_user_id)
        return created

    async def remove(self, telegram_user_id: int) -> bool:
        removed = await self._read.remove(telegram_user_id)
        await self._mirror.remove(telegram_user_id)
        return removed

    async def set_username(self, telegram_user_id: int, username: str) -> None:
        await self._read.set_username(telegram_user_id, username)
        await self._mirror.set_username(telegram_user_id, username)