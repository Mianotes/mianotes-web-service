from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import ApiToken, AppSetting, SessionToken, User

MASTER_PASSWORD_KEY = "master_password_hash"
SESSION_COOKIE_NAME = "mianotes_session"
SESSION_DAYS = 90
API_TOKEN_PREFIX = "mia"
ALLOWED_API_TOKEN_SCOPES = frozenset(
    {
        "admin",
        "users:read",
        "projects:read",
        "projects:write",
        "notes:read",
        "notes:write",
        "comments:write",
        "tags:read",
        "tags:write",
        "share:write",
        "tokens:read",
        "tokens:write",
    }
)


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


def normalize_api_token_scopes(scopes: Iterable[str]) -> list[str]:
    normalized = sorted({scope.strip() for scope in scopes if scope.strip()})
    invalid = [scope for scope in normalized if scope not in ALLOWED_API_TOKEN_SCOPES]
    if invalid:
        raise ValueError(f"Unsupported token scope: {', '.join(invalid)}")
    return normalized


def encode_api_token_scopes(scopes: Iterable[str]) -> str:
    return ",".join(normalize_api_token_scopes(scopes))


def decode_api_token_scopes(scopes: str) -> list[str]:
    if not scopes:
        return []
    return normalize_api_token_scopes(scopes.split(","))


def generate_api_token() -> str:
    return f"{API_TOKEN_PREFIX}_{secrets.token_urlsafe(32)}"


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_api_token(
    session: Session,
    user: User,
    *,
    name: str,
    scopes: Iterable[str],
    expires_at: datetime | None = None,
) -> tuple[ApiToken, str]:
    raw_token = generate_api_token()
    token = ApiToken(
        user_id=user.id,
        name=name,
        token_hash=hash_api_token(raw_token),
        token_prefix=raw_token[:12],
        scopes=encode_api_token_scopes(scopes),
        expires_at=expires_at,
    )
    session.add(token)
    return token, raw_token


def read_api_token(session: Session, raw_token: str | None) -> ApiToken | None:
    if not raw_token:
        return None
    token = session.scalars(
        select(ApiToken).where(ApiToken.token_hash == hash_api_token(raw_token))
    ).one_or_none()
    if token is None or token.revoked_at is not None:
        return None
    if token.expires_at is not None:
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            return None
    token.last_used_at = datetime.now(UTC)
    session.commit()
    return token
