from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx


@dataclass(frozen=True, slots=True)
class TelegramAllowlistEntry:
    telegram_user_id: int
    username: Optional[str]
    added_at: Optional[datetime]


class BotServiceClient:
    """HTTP-клиент bot-service: управление Telegram allowlist."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    async def list_telegram_users(self) -> list[TelegramAllowlistEntry]:
        data = await self._request("GET", "/internal/allowlist")

        return [
            TelegramAllowlistEntry(
                telegram_user_id=item["telegram_user_id"],
                username=item.get("username"),
                added_at=(
                    datetime.fromisoformat(item["added_at"])
                    if item.get("added_at")
                    else None
                ),
            )
            for item in data["items"]
        ]

    async def add_telegram_user(self, telegram_user_id: int) -> bool:
        data = await self._request(
            "POST",
            "/internal/allowlist",
            json={"telegram_user_id": telegram_user_id},
        )
        return bool(data["created"])

    async def remove_telegram_user(self, telegram_user_id: int) -> bool:
        try:
            await self._request(
                "DELETE",
                f"/internal/allowlist/{telegram_user_id}",
            )
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            raise