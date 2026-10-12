from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class OneTimePasscode(Base):
    __tablename__ = "one_time_passcodes"

    id = Column(Integer, primary_key=True)
    code_hash = Column(String, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    generated_by_telegram_id = Column(BigInteger, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)