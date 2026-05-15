from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import AppSetting

SHARE_SECRET_KEY = "share_secret"


def get_share_secret(session: Session, *, create: bool = False) -> str | None:
    setting = session.get(AppSetting, SHARE_SECRET_KEY)
    if setting is not None:
        return setting.value
    if not create:
        return None
    secret = secrets.token_urlsafe(32)
    session.add(AppSetting(key=SHARE_SECRET_KEY, value=secret))
    return secret


def generate_share_token() -> str:
    return secrets.token_urlsafe(18)


def hash_share_token(secret: str, token: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
