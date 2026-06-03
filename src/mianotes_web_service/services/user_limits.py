from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mianotes_web_service.core.config import Settings
from mianotes_web_service.db.models import User

SQLITE_MAX_USERS = 15
SQLITE_MAX_USERS_MESSAGE = (
    "Local Mianotes installations support up to 15 users. "
    "For larger teams, use a server database such as PostgreSQL."
)


def user_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(User)) or 0)


def enforce_user_capacity(session: Session, settings: Settings) -> None:
    if settings.database_adapter != "sqlite":
        return
    if user_count(session) >= SQLITE_MAX_USERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=SQLITE_MAX_USERS_MESSAGE,
        )
