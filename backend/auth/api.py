import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth.dependencies import optional_principal
from auth.ports import PasscodeVerifier
from auth.repository import SqlAdminCredentialRepository
from auth.sessions import SESSION_REGISTRY, create_session_token
from auth.tokens import SessionPrincipal, clear_session_cookie, set_session_cookie
from hashing import hash_secret, needs_rehash, verify_secret
from ratelimit import InMemoryRateLimiter

logger = logging.getLogger("legacy-backend.auth")


class AdminLogin(BaseModel):
    password: str


class OtpVerify(BaseModel):
    code: str


def create_auth_router(
    repo: SqlAdminCredentialRepository,
    passcode_verifier: PasscodeVerifier,
    login_limiter: InMemoryRateLimiter,
    otp_limiter: InMemoryRateLimiter,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/me")
    async def me(principal: Optional[SessionPrincipal] = Depends(optional_principal)):
        if principal is None:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "role": principal.role,
            "sub": principal.subject,
        }

    @router.post("/api/logout")
    async def logout(principal: Optional[SessionPrincipal] = Depends(optional_principal)):
        if principal is not None:
            SESSION_REGISTRY.revoke(principal.jti)
        response = JSONResponse({"ok": True})
        clear_session_cookie(response)
        return response

    @router.post("/api/admin/login")
    async def admin_login(payload: AdminLogin, request: Request):
        ip = request.client.host if request.client else "unknown"
        if login_limiter.is_limited(f"admin-login:{ip}"):
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

        admin = await repo.get_master()
        if admin is None or not verify_secret(admin.password_hash, payload.password):
            logger.warning("failed admin login from ip=%s", ip)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if needs_rehash(admin.password_hash):
            await repo.update_password_hash(hash_secret(payload.password))

        token = create_session_token("admin", "admin")
        response = JSONResponse({"ok": True, "role": "admin"})
        set_session_cookie(response, token)
        return response

    @router.post("/api/otp/verify")
    async def otp_verify(payload: OtpVerify, request: Request):
        ip = request.client.host if request.client else "unknown"
        if otp_limiter.is_limited(f"otp-verify:{ip}"):
            raise HTTPException(status_code=429, detail="Too many OTP attempts. Try again later.")

        otp_id = await passcode_verifier.verify(payload.code)
        if otp_id is None:
            raise HTTPException(status_code=401, detail="Invalid passcode")

        token = create_session_token("user", f"otp:{otp_id}")
        response = JSONResponse({"ok": True, "role": "user"})
        set_session_cookie(response, token)
        return response

    return router