from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from auth.models import AdminCredential
from hashing import hash_secret


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