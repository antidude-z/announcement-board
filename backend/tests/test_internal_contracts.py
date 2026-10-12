from fastapi import FastAPI
from fastapi.testclient import TestClient

from bot.api import create_allowlist_router
from m2m import internal_headers
from otp.api import create_otp_router
from ports import AllowlistEntry


class StubStore:
    def __init__(self):
        self.entries: dict[int, str | None] = {}

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


class StubIssuer:
    async def issue(self, telegram_user_id: int) -> str:
        return "STUBCODE"


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_otp_router(StubIssuer()))
    app.include_router(create_allowlist_router(StubStore()))
    return TestClient(app)


def test_otp_issue_requires_token():
    client = make_client()
    resp = client.post("/internal/otp/issue", json={"telegram_user_id": 1})
    assert resp.status_code == 401


def test_otp_issue_with_token():
    client = make_client()
    resp = client.post(
        "/internal/otp/issue", json={"telegram_user_id": 1}, headers=internal_headers()
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == "STUBCODE"


def test_allowlist_crud_and_status():
    client = make_client()
    h = internal_headers()

    assert client.get("/internal/allowlist", headers=h).json()["items"] == []
    assert client.post("/internal/allowlist", json={"telegram_user_id": 42}, headers=h).json()["created"] is True
    assert client.post("/internal/allowlist", json={"telegram_user_id": 42}, headers=h).json()["created"] is False
    assert client.get("/internal/allowlist/42/status", headers=h).json()["allowed"] is True
    assert client.patch("/internal/allowlist/42/username", json={"username": "alice"}, headers=h).status_code == 200
    assert client.delete("/internal/allowlist/42", headers=h).status_code == 200
    assert client.delete("/internal/allowlist/42", headers=h).status_code == 404