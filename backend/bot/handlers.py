import logging

from aiogram import Router, types
from aiogram.filters import Command, CommandStart

from ports import AllowlistStore, OtpIssuer
from bot.rate_limit import TgRateLimiter

logger = logging.getLogger("legacy-backend.bot")


def create_router(
    otp_issuer: OtpIssuer,
    allowlist_store: AllowlistStore,
    rate_limiter: TgRateLimiter,
) -> Router:
    router = Router()

    async def handle_get_code(message: types.Message) -> None:
        if not message.from_user:
            logger.warning("bot command without from_user")
            return

        telegram_id = message.from_user.id
        username = message.from_user.username
        logger.info("handle_get_code for telegram_id=%s", telegram_id)

        if rate_limiter.is_limited(telegram_id):
            await message.answer("Rate limited. Try again in a minute.")
            return

        if not await allowlist_store.is_allowed(telegram_id):
            logger.info("telegram_id=%s not in allowlist", telegram_id)
            await message.answer("Access Denied: Telegram ID is not authorized.")
            return

        if username:
            await allowlist_store.set_username(telegram_id, username)

        code = await otp_issuer.issue(telegram_id)
        logger.info("issued OTP for telegram_id=%s", telegram_id)
        await message.answer(
            "Your one-time passcode is:\n\n"
            f"{code}\n\n"
            "It expires in 5 minutes and can be used once."
        )

    @router.message(CommandStart())
    async def bot_start(message: types.Message) -> None:
        user_id = message.from_user.id if message.from_user else "unknown"
        logger.info("bot /start from user_id=%s", user_id)
        await handle_get_code(message)

    @router.message(Command("get_code"))
    async def bot_get_code(message: types.Message) -> None:
        user_id = message.from_user.id if message.from_user else "unknown"
        logger.info("bot /get_code from user_id=%s", user_id)
        await handle_get_code(message)

    return router