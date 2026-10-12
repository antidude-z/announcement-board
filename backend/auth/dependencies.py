from typing import Optional

from fastapi import HTTPException, Request

from auth.sessions import SESSION_REGISTRY
from auth.tokens import COOKIE_NAME, SessionPrincipal, decode_session_token


def get_principal(request: Request) -> Optional[SessionPrincipal]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    principal = decode_session_token(token)
    if principal is None:
        return None
    if not SESSION_REGISTRY.is_active(principal.jti):
        return None
    return principal


async def optional_principal(request: Request) -> Optional[SessionPrincipal]:
    return get_principal(request)


async def require_authenticated(request: Request) -> SessionPrincipal:
    principal = get_principal(request)
    if principal is None or principal.role not in ("user", "admin"):
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


async def require_admin(request: Request) -> SessionPrincipal:
    principal = get_principal(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return principal