from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import AppSetting

WORKSPACE_URL_KEY = "workspace_url"


def normalize_workspace_url(value: str | None) -> str | None:
    if value is None:
        return None
    clean_value = value.strip().rstrip("/")
    if not clean_value:
        return None
    parsed = urlparse(clean_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a full workspace address, such as https://notes.example.com.")
    return clean_value


def get_workspace_url(session: Session) -> str | None:
    setting = session.get(AppSetting, WORKSPACE_URL_KEY)
    if setting is None:
        return None
    return setting.value


def set_workspace_url(session: Session, value: str | None) -> str | None:
    next_value = normalize_workspace_url(value)
    setting = session.get(AppSetting, WORKSPACE_URL_KEY)
    if next_value is None:
        if setting is not None:
            session.delete(setting)
        return None
    if setting is None:
        session.add(AppSetting(key=WORKSPACE_URL_KEY, value=next_value))
    else:
        setting.value = next_value
    return next_value
