from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import AppSetting

STORAGE_CAPACITY_KEY = "storage_capacity"
STORAGE_CAPACITY_TTL_SECONDS = 3600


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _read_disk_usage(data_dir: Path) -> dict[str, int]:
    data_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(data_dir)
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
    }


def _read_data_dir_size(data_dir: Path) -> int:
    data_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for path in data_dir.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        total += path.stat().st_size
    return total


def _decode_snapshot(setting: AppSetting) -> dict[str, object] | None:
    try:
        payload = json.loads(setting.value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def get_storage_capacity(session: Session, data_dir: Path) -> dict[str, object]:
    now = datetime.now(UTC)
    setting = session.get(AppSetting, STORAGE_CAPACITY_KEY)
    if setting is not None:
        snapshot = _decode_snapshot(setting)
        cache_age = now - _utc(setting.updated_at)
        if snapshot is not None and cache_age < timedelta(seconds=STORAGE_CAPACITY_TTL_SECONDS):
            snapshot["refreshed_at"] = _utc(setting.updated_at).isoformat()
            snapshot["cache_expires_at"] = (
                _utc(setting.updated_at) + timedelta(seconds=STORAGE_CAPACITY_TTL_SECONDS)
            ).isoformat()
            return snapshot

    usage = _read_disk_usage(data_dir)
    total_bytes = usage["total_bytes"]
    used_bytes = usage["used_bytes"]
    used_percent = round((used_bytes / total_bytes) * 100, 2) if total_bytes else 0.0
    snapshot = {
        "data_dir": str(data_dir),
        **usage,
        "data_size_bytes": _read_data_dir_size(data_dir),
        "used_percent": used_percent,
        "cache_seconds": STORAGE_CAPACITY_TTL_SECONDS,
    }
    if setting is None:
        setting = AppSetting(key=STORAGE_CAPACITY_KEY, value=json.dumps(snapshot))
        session.add(setting)
    else:
        setting.value = json.dumps(snapshot)
        setting.updated_at = now
    session.commit()
    session.refresh(setting)
    snapshot["refreshed_at"] = _utc(setting.updated_at).isoformat()
    snapshot["cache_expires_at"] = (
        _utc(setting.updated_at) + timedelta(seconds=STORAGE_CAPACITY_TTL_SECONDS)
    ).isoformat()
    return snapshot
