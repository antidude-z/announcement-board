import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from hashing import hash_secret, verify_secret

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class OneTimePasscode(Base):
    __tablename__ = "one_time_passcodes"

    id = Column(Integer, primary_key=True)
    code_hash = Column(String, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    generated_by_telegram_id = Column(BigInteger, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class SqlOtpIssuer:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        ttl_seconds: int = 300,
    ):
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