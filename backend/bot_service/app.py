"""Отдельный процесс bot-service.

Владеет:
- aiogram polling;
- internal API allowlist;
- БД board_bot.

Выдачу OTP делегирует backend через POST /internal/otp/issue.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot_service.allowlist.api import create_allowlist_router
from bot_service.allowlist.models import Base as AllowlistBase
from bot_service.allowlist.repository import SqlAllowlistRepository
from bot_service.integrations.otp.http_issuer import HttpOtpIssuer
from bot_service.telegram.handlers import create_router
from bot_service.telegram.rate_limit import TgRateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("bot-service")

BOT_DATABASE_URL = os.getenv(
    "BOT_DATABASE_URL",
    "postgresql+asyncpg://board:board@db:5432/board_bot",
)
INTERNAL_BASE_URL = os.getenv("INTERNAL_BASE_URL", "http://backend:8000")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

engine = create_async_engine(BOT_DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

ALLOWLIST_REPOSITORY = SqlAllowlistRepository(SessionLocal)
PASSCODE_ISSUER = HttpOtpIssuer(INTERNAL_BASE_URL)
RATE_LIMITER = TgRateLimiter(max_requests=5, window_seconds=60)

DP = Dispatcher()
DP.include_router(create_router(PASSCODE_ISSUER, ALLOWLIST_REPOSITORY, RATE_LIMITER))

BOT = None
POLL_TASK = None


async def _run_polling():
    try:
        logger.info("aiogram polling task started (bot-service)")
        await DP.start_polling(BOT)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("aiogram polling crashed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global BOT, POLL_TASK

    async with engine.begin() as conn:
        await conn.run_sync(AllowlistBase.metadata.create_all)

    if TELEGRAM_BOT_TOKEN:
        BOT = Bot(token=TELEGRAM_BOT_TOKEN)
        POLL_TASK = asyncio.create_task(_run_polling())
    else:
        logger.warning("TELEGRAM_BOT_TOKEN is empty: bot-service serves only internal API")

    yield

    if POLL_TASK:
        POLL_TASK.cancel()
        try:
            await POLL_TASK
        except asyncio.CancelledError:
            pass

    if BOT:
        await BOT.session.close()

    await engine.dispose()


app = FastAPI(title="bot-service", lifespan=lifespan)
app.include_router(create_allowlist_router(ALLOWLIST_REPOSITORY))


@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "service": "bot-service",
        "polling": POLL_TASK is not None and not POLL_TASK.done(),
    }