import asyncio
import json
from datetime import datetime, timezone

import httpx

from integrations.telegram_allowlist.http_gateway import HttpTelegramAllowlistGateway


def make_gateway(handler: httpx.MockTransport) -> HttpTelegramAllowlistGateway:
    return HttpTelegramAllowlistGateway(
        "http://bot-service.test",
        transport=handler,
    )


def test_list_all_parses_items_and_sends_internal_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/internal/allowlist"
        assert request.headers["X-Internal-Token"] == "test-token"

        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "telegram_user_id": 42,
                        "username": "alice",
                        "added_at": "2026-01-01T00:00:00+00:00",
                    },
                    {
                        "telegram_user_id": 43,
                        "username": None,
                        "added_at": None,
                    },
                ]
            },
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    entries = asyncio.run(gateway.list_all())

    assert len(entries) == 2

    assert entries[0].telegram_user_id == 42
    assert entries[0].username == "alice"
    assert entries[0].added_at == datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert entries[1].telegram_user_id == 43
    assert entries[1].username is None
    assert entries[1].added_at is None


def test_add_returns_created_flag_and_sends_payload(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/internal/allowlist"
        assert request.headers["X-Internal-Token"] == "test-token"

        payload = json.loads(request.content)
        assert payload == {"telegram_user_id": 42}

        return httpx.Response(
            200,
            json={"telegram_user_id": 42, "created": True},
        )

    gateway = make_gateway(httpx.MockTransport(handler))

    assert asyncio.run(gateway.add(42)) is True


def test_remove_returns_true_on_success(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/internal/allowlist/42"
        assert request.headers["X-Internal-Token"] == "test-token"

        return httpx.Response(200, json={"ok": True})

    gateway = make_gateway(httpx.MockTransport(handler))

    assert asyncio.run(gateway.remove(42)) is True


def test_remove_returns_false_on_404(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/internal/allowlist/42"
        assert request.headers["X-Internal-Token"] == "test-token"

        return httpx.Response(
            404,
            json={"detail": "Telegram user not found"},
        )

    gateway = make_gateway(httpx.MockTransport(handler))

    assert asyncio.run(gateway.remove(42)) is False