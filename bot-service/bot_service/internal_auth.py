import os
import secrets

from fastapi import HTTPException, Request

INTERNAL_TOKEN_HEADER = "X-Internal-Token"
_DEFAULT_DEV_TOKEN = "dev-internal-token-change-me"


def get_internal_token() -> str:
    return os.getenv("INTERNAL_API_TOKEN", _DEFAULT_DEV_TOKEN)


async def require_internal_token(request: Request) -> None:
    provided = request.headers.get(INTERNAL_TOKEN_HEADER, "")
    if not provided or not secrets.compare_digest(provided, get_internal_token()):
        raise HTTPException(status_code=401, detail="Invalid internal token")


def internal_headers() -> dict[str, str]:
    return {INTERNAL_TOKEN_HEADER: get_internal_token()}