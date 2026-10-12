from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class TelegramAllowlist(Base):
    __tablename__ = "telegram_allowlist"

    telegram_user_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    added_at = Column(DateTime(timezone=True), default=utcnow)