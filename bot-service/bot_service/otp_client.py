import httpx


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
            )
            resp.raise_for_status()
            return resp.json()["code"]