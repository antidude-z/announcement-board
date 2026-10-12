import asyncio
import logging
import pathlib
import secrets
import uuid
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional

from bot import (
    BotBase,
    HttpAllowlistStore,
    HttpOtpIssuer,
    SqlAllowlistStore,
    TgRateLimiter,
    create_allowlist_router,
    create_router,
)
from otp import OtpBase, SqlOtpIssuer
from otp.api import create_otp_router
from otp.models import OneTimePasscode

import aiofiles
import jwt
from aiogram import Bot, Dispatcher
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import Boolean, BigInteger, Column, DateTime, Integer, String, Text, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

logger = logging.getLogger("legacy-backend")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://board:board@db:5432/board",
)

JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_hex(32)
COOKIE_NAME = "session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

ADMIN_INITIAL_PASSWORD = os.getenv("ADMIN_INITIAL_PASSWORD", "ChangeMe_Admin_123!")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

UPLOAD_DIR = pathlib.Path(os.getenv("UPLOAD_DIR", "/tmp/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# GLOBAL STATE
RATE_CACHE = {}
ACTIVE_SESSIONS = {}
BOT = None
BOT_POLL_TASK = None
DP = Dispatcher()

ph = PasswordHasher(type=Type.ID)
Base = declarative_base()

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def utcnow():
    return datetime.now(timezone.utc)


class AdminCredential(Base):
    __tablename__ = "admin_credentials"

    id = Column(Integer, primary_key=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    body_md = Column(Text, nullable=False)
    tags = Column(String, nullable=False, default="")
    video_url = Column(String, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AdminLogin(BaseModel):
    password: str


class OtpVerify(BaseModel):
    code: str


class TelegramUserIn(BaseModel):
    telegram_user_id: int


class PostIn(BaseModel):
    title: str
    body_md: str
    tags: str = ""
    video_url: str = ""


INTERNAL_BASE_URL = os.getenv("INTERNAL_BASE_URL", "http://127.0.0.1:8000")
BOT_SERVICE_URL = os.getenv("BOT_SERVICE_URL", "http://127.0.0.1:8000")
OTP_ISSUER_MODE = os.getenv("OTP_ISSUER_MODE", "local")
ALLOWLIST_STORE_MODE = os.getenv("ALLOWLIST_STORE_MODE", "local")

LOCAL_OTP_ISSUER = SqlOtpIssuer(AsyncSessionLocal)
LOCAL_ALLOWLIST_STORE = SqlAllowlistStore(AsyncSessionLocal)

# Серверная сторона внутренних API всегда на локальных адаптерах.
# Потребители выбирают реализацию флагами: local (in-process) или http (контракт).
OTP_ISSUER = LOCAL_OTP_ISSUER if OTP_ISSUER_MODE == "local" else HttpOtpIssuer(INTERNAL_BASE_URL)
ALLOWLIST_STORE = (
    LOCAL_ALLOWLIST_STORE if ALLOWLIST_STORE_MODE == "local" else HttpAllowlistStore(BOT_SERVICE_URL)
)

TG_RATE_LIMITER = TgRateLimiter(max_requests=5, window_seconds=60)
DP.include_router(create_router(OTP_ISSUER, ALLOWLIST_STORE, TG_RATE_LIMITER))


def is_rate_limited(key: str, max_requests: int = 5, window_seconds: int = 60) -> bool:
    now = utcnow().timestamp()
    entries = RATE_CACHE.get(key, [])
    entries = [entry for entry in entries if now - entry < window_seconds]

    if len(entries) >= max_requests:
        RATE_CACHE[key] = entries
        return True

    entries.append(now)
    RATE_CACHE[key] = entries
    return False


def create_session_token(role: str, subject: str) -> str:
    jti = str(uuid.uuid4())
    now = utcnow()
    exp = now + timedelta(seconds=86400)

    payload = {
        "sub": subject,
        "role": role,
        "jti": jti,
        "iat": now,
        "exp": exp,
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    ACTIVE_SESSIONS[jti] = exp.isoformat()
    return token


def set_session_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
        max_age=86400,
        path="/",
    )


def serialize_announcement(post: Announcement) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "body_md": post.body_md,
        "tags": post.tags,
        "video_url": post.video_url,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
    }

async def _run_bot_polling():
    try:
        logger.info("aiogram polling task started")
        await DP.start_polling(BOT)
    except asyncio.CancelledError:
        logger.info("aiogram polling task cancelled")
        raise
    except Exception:
        logger.exception("aiogram polling crashed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global BOT, BOT_POLL_TASK

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(BotBase.metadata.create_all)
        await conn.run_sync(OtpBase.metadata.create_all)

    async with AsyncSessionLocal() as session:
        admin = await session.get(AdminCredential, 1)
        if not admin:
            session.add(
                AdminCredential(
                    id=1,
                    password_hash=ph.hash(ADMIN_INITIAL_PASSWORD),
                )
            )
            await session.commit()

    if TELEGRAM_BOT_TOKEN:
        try:
            BOT = Bot(token=TELEGRAM_BOT_TOKEN)
            logger.info("Starting Telegram bot polling...")
            BOT_POLL_TASK = asyncio.create_task(_run_bot_polling())
        except Exception:
            logger.exception("Failed to initialize Telegram bot")
            BOT = None
            BOT_POLL_TASK = None
    else:
        logger.warning("TELEGRAM_BOT_TOKEN is empty/whitespace; Telegram bot disabled")

    yield

    if BOT_POLL_TASK:
        BOT_POLL_TASK.cancel()
        try:
            await BOT_POLL_TASK
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error while stopping bot task")

    if BOT:
        try:
            await BOT.session.close()
        except Exception:
            logger.exception("Error closing bot session")


app = FastAPI(title="Announcement Board Backend", lifespan=lifespan)

app.include_router(create_otp_router(LOCAL_OTP_ISSUER))
app.include_router(create_allowlist_router(LOCAL_ALLOWLIST_STORE))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-XSS-Protection"] = "0"
    return response


app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.get("/")
async def root():
    return {
        "name": "announcement-board",
        "mode": "legacy-monolith",
        "health": "/api/health",
    }


@app.get("/api/health")
async def health():
    return {"ok": True, "time": utcnow().isoformat()}


@app.get("/api/me")
async def me(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return {"authenticated": False}

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "role": payload.get("role"),
        "sub": payload.get("sub"),
    }


@app.post("/api/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
    )
    return response


@app.post("/api/admin/login")
async def admin_login(payload: AdminLogin, request: Request):
    ip = request.client.host if request.client else "unknown"

    if is_rate_limited(f"admin-login:{ip}", 5, 60):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many login attempts. Try again later."},
        )

    async with AsyncSessionLocal() as session:
        admin = await session.get(AdminCredential, 1)

        if not admin:
            return JSONResponse(status_code=401, content={"detail": "Invalid credentials"})

        try:
            ph.verify(admin.password_hash, payload.password)
        except (VerifyMismatchError, InvalidHashError, ValueError):
            return JSONResponse(status_code=401, content={"detail": "Invalid credentials"})

        if ph.check_needs_rehash(admin.password_hash):
            admin.password_hash = ph.hash(payload.password)
            await session.commit()

        token = create_session_token("admin", "admin")
        response = JSONResponse({"ok": True, "role": "admin"})
        set_session_cookie(response, token)
        return response


@app.post("/api/otp/verify")
async def otp_verify(payload: OtpVerify, request: Request):
    ip = request.client.host if request.client else "unknown"

    if is_rate_limited(f"otp-verify:{ip}", 5, 60):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many OTP attempts. Try again later."},
        )

    code = payload.code.strip().upper()

    if len(code) != 8:
        return JSONResponse(status_code=401, content={"detail": "Invalid passcode"})

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OneTimePasscode).where(
                OneTimePasscode.revoked == False,
                OneTimePasscode.expires_at > utcnow(),
            )
        )
        otp_rows = result.scalars().all()

        matched = None

        for otp in otp_rows:
            try:
                ph.verify(otp.code_hash, code)
                matched = otp
                break
            except (VerifyMismatchError, InvalidHashError, ValueError):
                continue

        if not matched:
            return JSONResponse(status_code=401, content={"detail": "Invalid passcode"})

        matched.revoked = True
        await session.commit()

        token = create_session_token("user", f"otp:{matched.id}")
        response = JSONResponse({"ok": True, "role": "user"})
        set_session_cookie(response, token)
        return response


@app.get("/api/posts")
async def list_posts(
    request: Request,
    page: int = Query(1),
    limit: int = Query(10),
    q: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    if payload.get("role") not in ("user", "admin"):
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    if page < 1:
        page = 1

    if limit < 1 or limit > 10:
        limit = 10

    async with AsyncSessionLocal() as session:
        stmt = select(Announcement).order_by(Announcement.created_at.desc())

        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Announcement.title.ilike(like),
                    Announcement.body_md.ilike(like),
                    Announcement.tags.ilike(like),
                )
            )

        if tag:
            stmt = stmt.where(Announcement.tags.ilike(f"%{tag}%"))

        stmt = stmt.offset((page - 1) * limit).limit(limit + 1)

        result = await session.execute(stmt)
        rows = result.scalars().all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        return {
            "items": [serialize_announcement(row) for row in rows],
            "page": page,
            "limit": limit,
            "has_more": has_more,
        }


@app.post("/api/posts")
async def create_post(payload: PostIn, request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    try:
        jwt_payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    if jwt_payload.get("role") != "admin":
        return JSONResponse(status_code=403, content={"detail": "Admin required"})

    title = payload.title.strip()
    body_md = payload.body_md.strip()
    tags = payload.tags.strip()
    video_url = payload.video_url.strip()

    if not title or not body_md:
        return JSONResponse(status_code=400, content={"detail": "Title and body are required"})

    async with AsyncSessionLocal() as session:
        post = Announcement(
            title=title,
            body_md=body_md,
            tags=tags,
            video_url=video_url,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return serialize_announcement(post)


@app.put("/api/posts/{post_id}")
async def update_post(post_id: int, payload: PostIn, request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    try:
        jwt_payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    if jwt_payload.get("role") != "admin":
        return JSONResponse(status_code=403, content={"detail": "Admin required"})

    title = payload.title.strip()
    body_md = payload.body_md.strip()
    tags = payload.tags.strip()
    video_url = payload.video_url.strip()

    if not title or not body_md:
        return JSONResponse(status_code=400, content={"detail": "Title and body are required"})

    async with AsyncSessionLocal() as session:
        post = await session.get(Announcement, post_id)
        if not post:
            return JSONResponse(status_code=404, content={"detail": "Post not found"})

        post.title = title
        post.body_md = body_md
        post.tags = tags
        post.video_url = video_url
        post.updated_at = utcnow()

        await session.commit()
        await session.refresh(post)
        return serialize_announcement(post)


@app.delete("/api/posts/{post_id}")
async def delete_post(post_id: int, request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    try:
        jwt_payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    if jwt_payload.get("role") != "admin":
        return JSONResponse(status_code=403, content={"detail": "Admin required"})

    async with AsyncSessionLocal() as session:
        post = await session.get(Announcement, post_id)
        if not post:
            return JSONResponse(status_code=404, content={"detail": "Post not found"})

        await session.delete(post)
        await session.commit()
        return {"ok": True}


@app.get("/api/telegram-users")
async def list_telegram_users(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    try:
        jwt_payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    if jwt_payload.get("role") != "admin":
        return JSONResponse(status_code=403, content={"detail": "Admin required"})

    entries = await ALLOWLIST_STORE.list_all()
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


@app.post("/api/telegram-users")
async def add_telegram_user(payload: TelegramUserIn, request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    try:
        jwt_payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    if jwt_payload.get("role") != "admin":
        return JSONResponse(status_code=403, content={"detail": "Admin required"})

    if payload.telegram_user_id <= 0:
        return JSONResponse(status_code=400, content={"detail": "Invalid Telegram user id"})

    created = await ALLOWLIST_STORE.add(payload.telegram_user_id)
    return {"telegram_user_id": payload.telegram_user_id, "already_exists": not created}


@app.delete("/api/telegram-users/{telegram_user_id}")
async def delete_telegram_user(telegram_user_id: int, request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    try:
        jwt_payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    if jwt_payload.get("role") != "admin":
        return JSONResponse(status_code=403, content={"detail": "Admin required"})

    removed = await ALLOWLIST_STORE.remove(telegram_user_id)
    if not removed:
        return JSONResponse(status_code=404, content={"detail": "Telegram user not found"})
    
    return {"ok": True}


@app.post("/api/uploads")
async def upload_image(request: Request, file: UploadFile = File(...)):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    try:
        jwt_payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid session"})

    if jwt_payload.get("role") != "admin":
        return JSONResponse(status_code=403, content={"detail": "Admin required"})

    filename = file.filename or ""
    suffix = pathlib.Path(filename).suffix.lower()

    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return JSONResponse(status_code=400, content={"detail": "Unsupported image type"})

    content = await file.read()

    if len(content) > 5 * 1024 * 1024:
        return JSONResponse(status_code=400, content={"detail": "File too large"})

    safe_name = f"{uuid.uuid4().hex}{suffix}"
    destination = UPLOAD_DIR / safe_name

    async with aiofiles.open(destination, "wb") as fh:
        await fh.write(content)

    return {"url": f"/uploads/{safe_name}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)