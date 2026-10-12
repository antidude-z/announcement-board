import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from bot_service.allowlist.repository import SqlAllowlistRepository
from bot_service.internal_auth import require_internal_token

logger = logging.getLogger("bot-service.allowlist.api")


class AddRequest(BaseModel):
    telegram_user_id: int


class UsernameRequest(BaseModel):
    username: str


def create_allowlist_router(repository: SqlAllowlistRepository) -> APIRouter:
    router = APIRouter(tags=["internal-allowlist"])

    @router.get("/internal/allowlist", dependencies=[Depends(require_internal_token)])
    async def list_all():
        entries = await repository.list_all()

        return {
            "items": [
                {
                    "telegram_user_id": e.telegram_user_id,
                    "username": e.username,
                    "added_at": e.added_at.isoformat() if e.added_at else None,
                }
                for e in entries
            ]
        }

    @router.get(
        "/internal/allowlist/{telegram_user_id}/status",
        dependencies=[Depends(require_internal_token)],
    )
    async def status(telegram_user_id: int):
        return {"allowed": await repository.is_allowed(telegram_user_id)}

    @router.post("/internal/allowlist", dependencies=[Depends(require_internal_token)])
    async def add(payload: AddRequest):
        created = await repository.add(payload.telegram_user_id)
        return {"telegram_user_id": payload.telegram_user_id, "created": created}

    @router.delete(
        "/internal/allowlist/{telegram_user_id}",
        dependencies=[Depends(require_internal_token)],
    )
    async def remove(telegram_user_id: int):
        removed = await repository.remove(telegram_user_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Telegram user not found")
        return {"ok": True}

    @router.patch(
        "/internal/allowlist/{telegram_user_id}/username",
        dependencies=[Depends(require_internal_token)],
    )
    async def set_username(telegram_user_id: int, payload: UsernameRequest):
        await repository.set_username(telegram_user_id, payload.username)
        return {"ok": True}

    return router