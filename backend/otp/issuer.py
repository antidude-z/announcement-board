import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from otp.models import OneTimePasscode, utcnow
from hashing import hash_secret


class SqlOtpIssuer:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], ttl_seconds: int = 300):
        self._session_factory = session_factory
        self._ttl_seconds = ttl_seconds

    async def issue(self, telegram_user_id: int) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        code = "".join(secrets.choice(alphabet) for _ in range(8))

        async with self._session_factory() as session:
            old = await session.execute(
                select(OneTimePasscode).where(
                    OneTimePasscode.generated_by_telegram_id == telegram_user_id,
                    OneTimePasscode.revoked == False,
                )
            )
            for old_code in old.scalars().all():
                old_code.revoked = True

            session.add(
                OneTimePasscode(
                    code_hash=hash_secret(code),
                    revoked=False,
                    generated_by_telegram_id=telegram_user_id,
                    expires_at=utcnow() + timedelta(seconds=self._ttl_seconds),
                )
            )
            await session.commit()

        return code