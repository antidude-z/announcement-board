import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.api import create_auth_router
from hashing import hash_secret
from ratelimit import InMemoryRateLimiter


class StubAdminRepo:
    def __init__(self, password: str):
        self.password_hash = hash_secret(password)
        self.updated_hash = None

    async def get_master(self):
        return types.SimpleNamespace(password_hash=self.password_hash)

    async def update_password_hash(self, new_hash: str) -> None:
        self.updated_hash = new_hash

    async def ensure_master(self, initial_password: str) -> None:
        pass


class StubOtpVerifier:
    def __init__(self, accept: str = "GOODCODE", otp_id: int = 77):
        self._accept = accept
        self._otp_id = otp_id

    async def verify(self, code: str):
        return self._otp_id if code.strip().upper() == self._accept else None


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(
        create_auth_router(
            StubAdminRepo("master-pass"),
            StubOtpVerifier(),
            InMemoryRateLimiter(max_requests=5, window_seconds=60),
            InMemoryRateLimiter(max_requests=5, window_seconds=60),
        )
    )
    return TestClient(app)


def test_login_wrong_password():
    client = make_client()
    resp = client.post("/api/admin/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_login_me_logout_revokes_session():
    client = make_client()
    assert client.post("/api/admin/login", json={"password": "master-pass"}).ok

    me = client.get("/api/me").json()
    assert me["authenticated"] is True and me["role"] == "admin"

    assert client.post("/api/logout").ok
    assert client.get("/api/me").json()["authenticated"] is False  # jti отозван


def test_otp_verify_issues_user_session():
    client = make_client()
    assert client.post("/api/otp/verify", json={"code": "GOODCODE"}).ok
    me = client.get("/api/me").json()
    assert me["authenticated"] is True and me["role"] == "user"

    assert client.post("/api/otp/verify", json={"code": "BADCODE"}).status_code == 401


def test_login_rate_limit():
    client = make_client()
    for _ in range(5):
        client.post("/api/admin/login", json={"password": "x"})
    resp = client.post("/api/admin/login", json={"password": "x"})
    assert resp.status_code == 429