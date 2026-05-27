from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import ApiToken, AppSetting, SessionToken, User

MASTER_PASSWORD_KEY = "master_password_hash"
WORKSPACE_ACCESS_MODE_KEY = "workspace_access_mode"
WORKSPACE_ACCESS_MODE_OPEN = "open"
WORKSPACE_ACCESS_MODE_ADMIN_ONLY = "admin_only"
INSTANCE_API_TOKEN_PUBLIC_KEY = "instance_api_token_public_key"
AGENT_SESSION_SIGNING_KEY = "agent_session_signing_key"
SESSION_COOKIE_NAME = "mianotes_session"
SESSION_DAYS = 90
AGENT_SESSION_HOURS = 12
API_TOKEN_PREFIX = "mia"
ALLOWED_API_TOKEN_SCOPES = frozenset(
    {
        "admin",
        "users:read",
        "folders:read",
        "folders:write",
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


def set_user_password(user: User, password: str) -> None:
    user.password_hash = hash_password(password)


def verify_user_password(user: User, password: str) -> bool:
    if not user.password_hash:
        return False
    return verify_password(password, user.password_hash)


def get_workspace_access_mode(session: Session) -> str:
    setting = session.get(AppSetting, WORKSPACE_ACCESS_MODE_KEY)
    if setting is None:
        return WORKSPACE_ACCESS_MODE_OPEN
    if setting.value not in {WORKSPACE_ACCESS_MODE_OPEN, WORKSPACE_ACCESS_MODE_ADMIN_ONLY}:
        return WORKSPACE_ACCESS_MODE_OPEN
    return setting.value


def set_workspace_access_mode(session: Session, mode: str) -> None:
    if mode not in {WORKSPACE_ACCESS_MODE_OPEN, WORKSPACE_ACCESS_MODE_ADMIN_ONLY}:
        raise ValueError("Unsupported workspace access mode")
    setting = session.get(AppSetting, WORKSPACE_ACCESS_MODE_KEY)
    if setting is None:
        session.add(AppSetting(key=WORKSPACE_ACCESS_MODE_KEY, value=mode))
        return
    setting.value = mode


def create_session_token(session: Session, user: User) -> SessionToken:
    token = SessionToken(
        id=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS),
    )
    session.add(token)
    return token


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _agent_session_signing_key(session: Session, *, create: bool = False) -> str | None:
    setting = session.get(AppSetting, AGENT_SESSION_SIGNING_KEY)
    if setting is not None:
        return setting.value
    if not create:
        return None
    secret = secrets.token_urlsafe(48)
    session.add(AppSetting(key=AGENT_SESSION_SIGNING_KEY, value=secret))
    return secret


def normalize_agent_client_name(client_name: str) -> str:
    normalized = " ".join(client_name.strip().split())
    if not normalized:
        raise ValueError("X-Mianotes-Client is required")
    if len(normalized) > 80:
        raise ValueError("X-Mianotes-Client must be 80 characters or fewer")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError("X-Mianotes-Client contains unsupported characters")
    return normalized


def create_agent_session_token(
    session: Session,
    *,
    user: User,
    client_name: str,
    client_key: str,
    scopes: Iterable[str],
    api_token_id: str | None = None,
    instance_token_public_key: str | None = None,
) -> tuple[str, datetime]:
    signing_key = _agent_session_signing_key(session, create=True)
    assert signing_key is not None
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=AGENT_SESSION_HOURS)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": "mianotes",
        "typ": "agent_session",
        "sub": user.id,
        "user_id": user.id,
        "client": normalize_agent_client_name(client_name),
        "client_key": client_key,
        "scopes": normalize_api_token_scopes(scopes),
        "api_token_id": api_token_id,
        "instance_token_public_key": instance_token_public_key,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(signing_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}", expires_at


def decode_agent_session_token(session: Session, raw_token: str) -> dict[str, object] | None:
    signing_key = _agent_session_signing_key(session)
    if signing_key is None:
        return None
    try:
        encoded_header, encoded_payload, encoded_signature = raw_token.split(".", 2)
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(
            signing_key.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        actual_signature = _base64url_decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, actual_signature):
            return None
        header = json.loads(_base64url_decode(encoded_header))
        payload = json.loads(_base64url_decode(encoded_payload))
    except (binascii.Error, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        return None
    if payload.get("iss") != "mianotes" or payload.get("typ") != "agent_session":
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(datetime.now(UTC).timestamp()):
        return None
    return payload


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


def sync_instance_api_token_public_key(session: Session, raw_token: str) -> str:
    """Store the public hash for the service-wide API token in this database."""

    token_hash = hash_api_token(raw_token)
    setting = session.get(AppSetting, INSTANCE_API_TOKEN_PUBLIC_KEY)
    if setting is None:
        session.add(AppSetting(key=INSTANCE_API_TOKEN_PUBLIC_KEY, value=token_hash))
        session.commit()
        return token_hash
    if setting.value != token_hash:
        setting.value = token_hash
        session.commit()
    return token_hash


def verify_instance_api_token(session: Session, raw_token: str | None) -> bool:
    if not raw_token:
        return False
    setting = session.get(AppSetting, INSTANCE_API_TOKEN_PUBLIC_KEY)
    if setting is None:
        return False
    return hmac.compare_digest(hash_api_token(raw_token), setting.value)


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
