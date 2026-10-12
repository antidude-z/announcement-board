from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hashing import verify_secret
from otp.models import OneTimePasscode, utcnow


class SqlOtpVerifier:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def verify(self, code: str) -> Optional[int]:
        code = code.strip().upper()
        if len(code) != 8:
            return None

        async with self._session_factory() as session:
            result = await session.execute(
                select(OneTimePasscode).where(
                    OneTimePasscode.revoked == False,
                    OneTimePasscode.expires_at > utcnow(),
                )
            )
            for otp in result.scalars().all():
                if verify_secret(otp.code_hash, code):
                    otp.revoked = True
                    await session.commit()
                    return otp.id
        return None