from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class AllowlistEntry:
    telegram_user_id: int
    username: Optional[str]
    added_at: Optional[datetime]