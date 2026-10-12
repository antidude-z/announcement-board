from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ports import AllowlistEntry
from bot.models import TelegramAllowlist


class SqlAllowlistStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def is_allowed(self, telegram_user_id: int) -> bool:
        async with self._session_factory() as session:
            entry = await session.get(TelegramAllowlist, telegram_user_id)
            return entry is not None

    async def list_all(self) -> list[AllowlistEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TelegramAllowlist).order_by(TelegramAllowlist.added_at.desc())
            )
            return [
                AllowlistEntry(
                    telegram_user_id=row.telegram_user_id,
                    username=row.username,
                    added_at=row.added_at,
                )
                for row in result.scalars().all()
            ]

    async def add(self, telegram_user_id: int) -> bool:
        async with self._session_factory() as session:
            existing = await session.get(TelegramAllowlist, telegram_user_id)
            if existing:
                return False
            session.add(TelegramAllowlist(telegram_user_id=telegram_user_id))
            await session.commit()
            return True

    async def remove(self, telegram_user_id: int) -> bool:
        async with self._session_factory() as session:
            entry = await session.get(TelegramAllowlist, telegram_user_id)
            if not entry:
                return False
            await session.delete(entry)
            await session.commit()
            return True

    async def set_username(self, telegram_user_id: int, username: str) -> None:
        async with self._session_factory() as session:
            entry = await session.get(TelegramAllowlist, telegram_user_id)
            if entry and entry.username != username:
                entry.username = username
                await session.commit()