from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import AppSetting, SessionToken, User

MASTER_PASSWORD_KEY = "master_password_hash"
SESSION_COOKIE_NAME = "mianotes_session"
SESSION_DAYS = 90


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 390_000)
    return "pbkdf2_sha256$390000${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def get_master_password_hash(session: Session) -> str | None:
    setting = session.get(AppSetting, MASTER_PASSWORD_KEY)
    return setting.value if setting is not None else None


def set_master_password(session: Session, password: str) -> None:
    setting = session.get(AppSetting, MASTER_PASSWORD_KEY)
    if setting is None:
        session.add(AppSetting(key=MASTER_PASSWORD_KEY, value=hash_password(password)))
        return
    setting.value = hash_password(password)


def verify_master_password(session: Session, password: str) -> bool:
    stored_hash = get_master_password_hash(session)
    if stored_hash is None:
        return False
    return verify_password(password, stored_hash)


def create_session_token(session: Session, user: User) -> SessionToken:
    token = SessionToken(
        id=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS),
    )
    session.add(token)
    return token


def read_session_user(session: Session, token_id: str | None) -> User | None:
    if not token_id:
        return None
    token = session.get(SessionToken, token_id)
    if token is None:
        return None
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        session.delete(token)
        session.commit()
        return None
    return token.user
