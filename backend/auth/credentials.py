from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from hashing import hash_secret

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class AdminCredential(Base):
    __tablename__ = "admin_credentials"

    id = Column(Integer, primary_key=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class SqlAdminCredentialRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def get_master(self) -> Optional[AdminCredential]:
        async with self._session_factory() as session:
            return await session.get(AdminCredential, 1)

    async def update_password_hash(self, new_hash: str) -> None:
        async with self._session_factory() as session:
            admin = await session.get(AdminCredential, 1)
            if admin:
                admin.password_hash = new_hash
                await session.commit()

    async def ensure_master(self, initial_password: str) -> None:
        async with self._session_factory() as session:
            admin = await session.get(AdminCredential, 1)
            if not admin:
                session.add(
                    AdminCredential(id=1, password_hash=hash_secret(initial_password))
                )
                await session.commit()