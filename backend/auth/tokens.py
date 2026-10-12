import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_hex(32)
COOKIE_NAME = "session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
SESSION_TTL_SECONDS = 86400


@dataclass(frozen=True)
class SessionPrincipal:
    role: str
    subject: str
    jti: str


def encode_session_token(role: str, subject: str) -> tuple[str, str, datetime]:
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
    payload = {"sub": subject, "role": role, "jti": jti, "iat": now, "exp": expires_at}
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token, jti, expires_at


def decode_session_token(token: str) -> Optional[SessionPrincipal]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None
    return SessionPrincipal(
        role=payload.get("role", ""),
        subject=payload.get("sub", ""),
        jti=payload.get("jti", ""),
    )


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
    )