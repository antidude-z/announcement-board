from datetime import datetime

import httpx

from m2m import internal_headers
from ports import AllowlistEntry


class HttpOtpIssuer:
    """Клиент монолита: POST /internal/otp/issue."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def issue(self, telegram_user_id: int) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/internal/otp/issue",
                json={"telegram_user_id": telegram_user_id},
                headers=internal_headers(),
            )
            resp.raise_for_status()
            return resp.json()["code"]


class HttpAllowlistStore:
    """Клиент bot-service: /internal/allowlist*."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def _request(self, method: str, path: str, **kwargs):
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=internal_headers(),
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()

    async def is_allowed(self, telegram_user_id: int) -> bool:
        data = await self._request("GET", f"/internal/allowlist/{telegram_user_id}/status")
        return bool(data["allowed"])

    async def list_all(self) -> list[AllowlistEntry]:
        data = await self._request("GET", "/internal/allowlist")
        return [
            AllowlistEntry(
                telegram_user_id=item["telegram_user_id"],
                username=item.get("username"),
                added_at=(
                    datetime.fromisoformat(item["added_at"]) if item.get("added_at") else None
                ),
            )
            for item in data["items"]
        ]

    async def add(self, telegram_user_id: int) -> bool:
        data = await self._request(
            "POST", "/internal/allowlist", json={"telegram_user_id": telegram_user_id}
        )
        return bool(data["created"])

    async def remove(self, telegram_user_id: int) -> bool:
        try:
            await self._request("DELETE", f"/internal/allowlist/{telegram_user_id}")
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            raise

    async def set_username(self, telegram_user_id: int, username: str) -> None:
        await self._request(
            "PATCH",
            f"/internal/allowlist/{telegram_user_id}/username",
            json={"username": username},
        )