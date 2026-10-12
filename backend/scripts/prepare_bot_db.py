"""Миграция allowlist в собственную БД бота (шаг 3).

Идемпотентно: ensure database -> create tables -> upsert-копия строк.
Безопасно перезапускать; подходит для синхронизации дрейфа при dual-write.
"""
import asyncio
import argparse
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


async def copy_rows(src_url: str, dst_url: str, ensure_tables_at_dst: bool = True) -> int:
    src_engine = create_async_engine(src_url)
    dst_engine = create_async_engine(dst_url)

    if ensure_tables_at_dst:
        async with dst_engine.begin() as conn:
            await conn.run_sync(BotBase.metadata.create_all)

    src_factory = async_sessionmaker(src_engine, expire_on_commit=False)
    dst_factory = async_sessionmaker(dst_engine, expire_on_commit=False)

    synced = 0
    async with src_factory() as src_session:
        rows = (await src_session.execute(select(TelegramAllowlist))).scalars().all()
        async with dst_factory() as dst_session:
            for row in rows:
                existing = await dst_session.get(TelegramAllowlist, row.telegram_user_id)
                if existing:
                    existing.username = row.username
                    existing.added_at = row.added_at
                else:
                    dst_session.add(
                        TelegramAllowlist(
                            telegram_user_id=row.telegram_user_id,
                            username=row.username,
                            added_at=row.added_at,
                        )
                    )
                synced += 1
            await dst_session.commit()

    await src_engine.dispose()
    await dst_engine.dispose()
    return synced


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync telegram_allowlist between monolith DB and bot DB"
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="copy bot DB -> monolith DB (rollback sync after BOT_MODE=external)",
    )
    args = parser.parse_args()

    if args.reverse:
        synced = await copy_rows(BOT_DB_URL, MONOLITH_DB_URL, ensure_tables_at_dst=False)
        print(f"reverse sync (bot -> monolith) rows: {synced}")
    else:
        await ensure_database()
        synced = await copy_rows(MONOLITH_DB_URL, BOT_DB_URL)
        print(f"allowlist rows synced (monolith -> bot): {synced}")

if __name__ == "__main__":
    asyncio.run(main())