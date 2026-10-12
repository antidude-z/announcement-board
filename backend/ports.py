from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class AllowlistEntry:
    telegram_user_id: int
    username: Optional[str]
    added_at: Optional[datetime]


@runtime_checkable
class AllowlistStore(Protocol):
    async def is_allowed(self, telegram_user_id: int) -> bool: ...
    async def list_all(self) -> list[AllowlistEntry]: ...
    async def add(self, telegram_user_id: int) -> bool: ...
    async def remove(self, telegram_user_id: int) -> bool: ...
    async def set_username(self, telegram_user_id: int, username: str) -> None: ...