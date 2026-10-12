import asyncio
from typing import Optional

from bot.dual_write import DualWriteAllowlistStore
from ports import AllowlistEntry


class InMemoryStore:
    def __init__(self):
        self.entries: dict[int, Optional[str]] = {}

    async def is_allowed(self, telegram_user_id: int) -> bool:
        return telegram_user_id in self.entries

    async def list_all(self) -> list[AllowlistEntry]:
        return [
            AllowlistEntry(telegram_user_id=i, username=u, added_at=None)
            for i, u in self.entries.items()
        ]

    async def add(self, telegram_user_id: int) -> bool:
        if telegram_user_id in self.entries:
            return False
        self.entries[telegram_user_id] = None
        return True

    async def remove(self, telegram_user_id: int) -> bool:
        if telegram_user_id not in self.entries:
            return False
        del self.entries[telegram_user_id]
        return True

    async def set_username(self, telegram_user_id: int, username: str) -> None:
        self.entries[telegram_user_id] = username


def test_add_and_remove_write_to_both_stores():
    async def scenario():
        read_store, mirror_store = InMemoryStore(), InMemoryStore()
        store = DualWriteAllowlistStore(read_store, mirror_store)

        assert await store.add(42) is True
        assert 42 in read_store.entries and 42 in mirror_store.entries

        assert await store.add(42) is False  # идемпотентно

        await store.set_username(42, "alice")
        assert read_store.entries[42] == "alice"
        assert mirror_store.entries[42] == "alice"

        assert await store.remove(42) is True
        assert 42 not in read_store.entries and 42 not in mirror_store.entries

    asyncio.run(scenario())


def test_reads_come_from_read_store_only():
    async def scenario():
        read_store, mirror_store = InMemoryStore(), InMemoryStore()
        mirror_store.entries[7] = None  # есть только в mirror
        store = DualWriteAllowlistStore(read_store, mirror_store)

        assert await store.is_allowed(7) is False
        assert await store.list_all() == []

    asyncio.run(scenario())