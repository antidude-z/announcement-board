"""Миграция allowlist в собственную БД бота (шаг 3).

Идемпотентно: ensure database -> create tables -> upsert-копия строк.
Безопасно перезапускать; подходит для синхронизации дрейфа при dual-write.
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.append(str(Path(__file__).resolve().parents[1]))

from bot.models import Base as BotBase  # noqa: E402
from bot.models import TelegramAllowlist  # noqa: E402

MONOLITH_DB_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://board:board@db:5432/board")
BOT_DB_URL = os.getenv("BOT_DATABASE_URL", "postgresql+asyncpg://board:board@db:5432/board_bot")
BOT_DB_NAME = os.getenv("BOT_DB_NAME", "board_bot")
ADMIN_URL = os.getenv("BOT_POSTGRES_ADMIN_URL", "postgresql://board:board@db:5432/postgres")


async def ensure_database() -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", BOT_DB_NAME)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{BOT_DB_NAME}"')
            print(f"created database {BOT_DB_NAME}")
        else:
            print(f"database {BOT_DB_NAME} already exists")
    finally:
        await conn.close()


async def create_tables_and_copy() -> int:
    bot_engine = create_async_engine(BOT_DB_URL)
    mono_engine = create_async_engine(MONOLITH_DB_URL)

    async with bot_engine.begin() as conn:
        await conn.run_sync(BotBase.metadata.create_all)

    mono_session_factory = async_sessionmaker(mono_engine, expire_on_commit=False)
    bot_session_factory = async_sessionmaker(bot_engine, expire_on_commit=False)

    synced = 0
    async with mono_session_factory() as mono_session:
        rows = (await mono_session.execute(select(TelegramAllowlist))).scalars().all()

        async with bot_session_factory() as bot_session:
            for row in rows:
                existing = await bot_session.get(TelegramAllowlist, row.telegram_user_id)
                if existing:
                    existing.username = row.username
                    existing.added_at = row.added_at
                else:
                    bot_session.add(
                        TelegramAllowlist(
                            telegram_user_id=row.telegram_user_id,
                            username=row.username,
                            added_at=row.added_at,
                        )
                    )
                synced += 1
            await bot_session.commit()

    await bot_engine.dispose()
    await mono_engine.dispose()
    return synced


async def main() -> None:
    await ensure_database()
    synced = await create_tables_and_copy()
    print(f"allowlist rows synced: {synced}")


if __name__ == "__main__":
    asyncio.run(main())