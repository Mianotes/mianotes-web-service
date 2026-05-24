from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import AdminUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db import session as db_session
from mianotes_web_service.db.init import create_database
from mianotes_web_service.db.models import MiaJob
from mianotes_web_service.domain.schemas import (
    ServiceApiKeyRead,
    StorageLocationCreate,
    StorageLocationRead,
    StorageSettingsRead,
    StorageSwitchRead,
    StorageSwitchRequest,
)
from mianotes_web_service.services.auth import (
    SESSION_COOKIE_NAME,
    generate_api_token,
    sync_instance_api_token_public_key,
)
from mianotes_web_service.services.job_runner import InProcessJobRunner
from mianotes_web_service.services.storage_settings import (
    StorageConfig,
    activate_storage_location,
    add_storage_location,
    read_storage_config,
    set_api_token,
    write_storage_config,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _database_url(folder_path: Path, database_file: str) -> str:
    return f"sqlite:///{folder_path / database_file}"


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _database_stats(database_path: Path) -> tuple[int | None, int | None, datetime | None]:
    if not database_path.exists():
        return None, None, None
    try:
        with sqlite3.connect(database_path) as connection:
            notes_count = connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            users_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            last_updated = connection.execute("SELECT MAX(updated_at) FROM notes").fetchone()[0]
    except sqlite3.Error:
        return None, None, None
    return int(notes_count), int(users_count), _parse_datetime(last_updated)


def _read_storage_config() -> StorageConfig:
    settings = get_settings()
    return read_storage_config(settings.storage_config_path, default_data_dir=settings.data_dir)


def _storage_response(config: StorageConfig) -> StorageSettingsRead:
    active_folder_path = config.active_folder_path
    locations: list[StorageLocationRead] = []
    for location in config.locations:
        database_path = location.folder_path / config.database_file
        notes_count, users_count, last_updated_at = _database_stats(database_path)
        locations.append(
            StorageLocationRead(
                id=location.id,
                name=location.name,
                folder_path=str(location.folder_path),
                database_path=str(database_path),
                is_active=location.id == config.active_location,
                database_exists=database_path.exists(),
                notes_count=notes_count,
                users_count=users_count,
                last_updated_at=last_updated_at,
            )
        )
    return StorageSettingsRead(
        active_location=config.active_location,
        database_file=config.database_file,
        data_dir=str(active_folder_path),
        database_path=str(active_folder_path / config.database_file),
        locations=locations,
    )


def _queued_or_running_jobs(session: Session) -> int:
    total = session.scalar(
        select(func.count())
        .select_from(MiaJob)
        .where(MiaJob.status.in_(["queued", "running"]))
    )
    return int(total or 0)


@router.get("/storage", response_model=StorageSettingsRead)
def storage_settings(_: AdminUser) -> StorageSettingsRead:
    return _storage_response(_read_storage_config())


@router.post("/api-key", response_model=ServiceApiKeyRead, status_code=status.HTTP_201_CREATED)
def create_service_api_key(session: SessionDep, _: AdminUser) -> ServiceApiKeyRead:
    raw_token = generate_api_token()
    config = _read_storage_config()
    write_storage_config(get_settings().storage_config_path, set_api_token(config, raw_token))
    get_settings().api_token = raw_token
    sync_instance_api_token_public_key(session, raw_token)
    return ServiceApiKeyRead(token=raw_token)


@router.post("/storage/locations", response_model=StorageSettingsRead)
def create_storage_location(payload: StorageLocationCreate, _: AdminUser) -> StorageSettingsRead:
    config = _read_storage_config()
    try:
        next_config = add_storage_location(
            config,
            name=payload.name,
            folder_path=payload.folder_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    new_location = next_config.locations[-1]
    new_engine = db_session.create_database_engine(
        _database_url(new_location.folder_path, next_config.database_file)
    )
    try:
        create_database(new_engine)
    finally:
        new_engine.dispose()
    write_storage_config(get_settings().storage_config_path, next_config)
    return _storage_response(next_config)


@router.patch("/storage/active", response_model=StorageSwitchRead)
def switch_storage(
    payload: StorageSwitchRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    _: AdminUser,
) -> StorageSwitchRead:
    if _queued_or_running_jobs(session) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mia is still processing notes. Try switching databases when those jobs finish.",
        )

    config = _read_storage_config()
    try:
        next_config = activate_storage_location(config, location_id=payload.location_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    write_storage_config(get_settings().storage_config_path, next_config)
    new_database_url = _database_url(next_config.active_folder_path, next_config.database_file)
    settings = get_settings()
    settings.data_dir = next_config.active_folder_path
    settings.database_url = new_database_url

    session.close()
    new_engine = db_session.reconfigure_database(new_database_url)
    create_database(new_engine)
    request.app.state.job_runner = InProcessJobRunner(db_session.SessionLocal)
    response.delete_cookie(SESSION_COOKIE_NAME)

    return StorageSwitchRead(storage=_storage_response(next_config), session_ended=True)
