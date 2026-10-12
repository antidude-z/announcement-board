import logging
import os
import pathlib
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import aiofiles
from fastapi import Depends, FastAPI, File, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Text, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from auth import (
    AuthBase,
    SqlAdminCredentialRepository,
    create_auth_router,
    require_admin,
    require_authenticated,
)
from auth.tokens import SessionPrincipal
from bot_service_client import BotServiceClient
from otp import OtpBase, SqlOtpIssuer, SqlOtpVerifier
from otp.api import create_otp_router
from ratelimit import InMemoryRateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("legacy-backend")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://board:board@db:5432/board",
)
ADMIN_INITIAL_PASSWORD = os.getenv("ADMIN_INITIAL_PASSWORD", "ChangeMe_Admin_123!")
UPLOAD_DIR = pathlib.Path(os.getenv("UPLOAD_DIR", "/tmp/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

Base = declarative_base()
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def utcnow():
    return datetime.now(timezone.utc)


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    body_md = Column(Text, nullable=False)
    tags = Column(String, nullable=False, default="")
    video_url = Column(String, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TelegramUserIn(BaseModel):
    telegram_user_id: int


class PostIn(BaseModel):
    title: str
    body_md: str
    tags: str = ""
    video_url: str = ""


BOT_SERVICE_URL = os.getenv("BOT_SERVICE_URL", "http://bot:8001")

PASSCODE_ISSUER: SqlOtpIssuer = SqlOtpIssuer(AsyncSessionLocal)
BOT_SERVICE_CLIENT = BotServiceClient(BOT_SERVICE_URL)

ADMIN_REPO = SqlAdminCredentialRepository(AsyncSessionLocal)
PASSCODE_VERIFIER: SqlOtpVerifier = SqlOtpVerifier(AsyncSessionLocal)
LOGIN_LIMITER = InMemoryRateLimiter(max_requests=5, window_seconds=60)
OTP_LIMITER = InMemoryRateLimiter(max_requests=5, window_seconds=60)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(OtpBase.metadata.create_all)
        await conn.run_sync(AuthBase.metadata.create_all)

    await ADMIN_REPO.ensure_master(ADMIN_INITIAL_PASSWORD)

    yield

    await engine.dispose()


app = FastAPI(title="Announcement Board Backend", lifespan=lifespan)

app.include_router(create_otp_router(PASSCODE_ISSUER))
app.include_router(
    create_auth_router(ADMIN_REPO, PASSCODE_VERIFIER, LOGIN_LIMITER, OTP_LIMITER)
)

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
        "mode": "modular-monolith",
        "health": "/api/health",
    }


@app.get("/api/health")
async def health():
    return {"ok": True, "time": utcnow().isoformat()}


@app.get("/api/posts")
async def list_posts(
    principal: SessionPrincipal = Depends(require_authenticated),
    page: int = Query(1),
    limit: int = Query(10),
    q: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
):
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
async def create_post(
    payload: PostIn,
    principal: SessionPrincipal = Depends(require_admin),
):
    title = payload.title.strip()
    body_md = payload.body_md.strip()
    tags = payload.tags.strip()
    video_url = payload.video_url.strip()

    if not title or not body_md:
        return JSONResponse(status_code=400, content={"detail": "Title and body are required"})

    async with AsyncSessionLocal() as session:
        post = Announcement(title=title, body_md=body_md, tags=tags, video_url=video_url)
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return serialize_announcement(post)


@app.put("/api/posts/{post_id}")
async def update_post(
    post_id: int,
    payload: PostIn,
    principal: SessionPrincipal = Depends(require_admin),
):
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
async def delete_post(
    post_id: int,
    principal: SessionPrincipal = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        post = await session.get(Announcement, post_id)
        if not post:
            return JSONResponse(status_code=404, content={"detail": "Post not found"})

        await session.delete(post)
        await session.commit()
        return {"ok": True}


@app.get("/api/telegram-users")
async def list_telegram_users(principal: SessionPrincipal = Depends(require_admin)):
    entries = await BOT_SERVICE_CLIENT.list_telegram_users()
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
async def add_telegram_user(
    payload: TelegramUserIn,
    principal: SessionPrincipal = Depends(require_admin),
):
    if payload.telegram_user_id <= 0:
        return JSONResponse(status_code=400, content={"detail": "Invalid Telegram user id"})

    created = await BOT_SERVICE_CLIENT.add_telegram_user(payload.telegram_user_id)
    return {"telegram_user_id": payload.telegram_user_id, "already_exists": not created}


@app.delete("/api/telegram-users/{telegram_user_id}")
async def delete_telegram_user(
    telegram_user_id: int,
    principal: SessionPrincipal = Depends(require_admin),
):
    removed = await BOT_SERVICE_CLIENT.remove_telegram_user(telegram_user_id)
    if not removed:
        return JSONResponse(status_code=404, content={"detail": "Telegram user not found"})
    return {"ok": True}


@app.post("/api/uploads")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    principal: SessionPrincipal = Depends(require_admin),
):
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