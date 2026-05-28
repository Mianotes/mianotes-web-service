from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, status

from mianotes_web_service.api.dependencies import AdminUser, CurrentUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db import session as db_session
from mianotes_web_service.db.init import create_workspace_database
from mianotes_web_service.db.models import SessionToken
from mianotes_web_service.domain.schemas import (
    ServiceApiKeyRead,
    ShareSettingsRead,
    ShareSettingsUpdate,
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
from mianotes_web_service.services.env_file import (
    ensure_service_api_url,
    service_env_file_path,
    upsert_env_value,
)
from mianotes_web_service.services.share_settings import get_workspace_url, set_workspace_url
from mianotes_web_service.services.storage_settings import (
    StorageConfig,
    add_storage_location,
    read_storage_config,
    storage_database_path,
    write_storage_config,
)
from mianotes_web_service.services.workspace_context import WorkspaceContext

router = APIRouter(prefix="/settings", tags=["settings"])


def _database_url(folder_path: Path, database_file: str) -> str:
    return f"sqlite:///{storage_database_path(folder_path, database_file)}"


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
            last_updated = connection.execute("SELECT MAX(updated_at) FROM notes").fetchone()[0]
    except sqlite3.Error:
        return None, None, None
    return int(notes_count), None, _parse_datetime(last_updated)


def _read_storage_config() -> StorageConfig:
    settings = get_settings()
    return read_storage_config(settings.storage_config_path, default_data_dir=settings.data_dir)


def _storage_response(
    config: StorageConfig,
    *,
    active_location: str | None = None,
) -> StorageSettingsRead:
    active_location = active_location or config.active_location
    active_folder_path = next(
        (location.folder_path for location in config.locations if location.id == active_location),
        config.active_folder_path,
    )
    locations: list[StorageLocationRead] = []
    for location in config.locations:
        database_path = storage_database_path(location.folder_path, config.database_file)
        notes_count, users_count, last_updated_at = _database_stats(database_path)
        locations.append(
            StorageLocationRead(
                id=location.id,
                name=location.name,
                folder_path=str(location.folder_path),
                database_path=str(database_path),
                is_active=location.id == active_location,
                database_exists=database_path.exists(),
                notes_count=notes_count,
                users_count=users_count,
                last_updated_at=last_updated_at,
            )
        )
    return StorageSettingsRead(
        active_location=active_location,
        database_file=config.database_file,
        data_dir=str(active_folder_path),
        database_path=str(storage_database_path(active_folder_path, config.database_file)),
        locations=locations,
    )


@router.get("/storage", response_model=StorageSettingsRead)
def storage_settings(session: SessionDep, _: CurrentUser) -> StorageSettingsRead:
    workspace = session.info.get("workspace")
    active_location = workspace.id if isinstance(workspace, WorkspaceContext) else None
    return _storage_response(_read_storage_config(), active_location=active_location)


@router.post("/api-key", response_model=ServiceApiKeyRead, status_code=status.HTTP_201_CREATED)
def create_service_api_key(session: SessionDep, _: AdminUser) -> ServiceApiKeyRead:
    raw_token = generate_api_token()
    env_file_path = service_env_file_path()
    try:
        api_url = ensure_service_api_url(env_file_path)
        upsert_env_value(env_file_path, "MIANOTES_API_KEY", raw_token)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not write the API key to the Mianotes environment file.",
        ) from exc

    os.environ["MIANOTES_API_KEY"] = raw_token
    get_settings().api_token = raw_token
    write_storage_config(get_settings().storage_config_path, _read_storage_config())
    sync_instance_api_token_public_key(session, raw_token)
    return ServiceApiKeyRead(token=raw_token, api_url=api_url)


@router.get("/share", response_model=ShareSettingsRead)
def share_settings(session: SessionDep, _: CurrentUser) -> ShareSettingsRead:
    return ShareSettingsRead(workspace_url=get_workspace_url(session))


@router.patch("/share", response_model=ShareSettingsRead)
def update_share_settings(
    payload: ShareSettingsUpdate,
    session: SessionDep,
    _: AdminUser,
) -> ShareSettingsRead:
    try:
        workspace_url = set_workspace_url(session, payload.workspace_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return ShareSettingsRead(workspace_url=workspace_url)


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

    new_location = next_config.locations[0]
    new_engine = db_session.create_database_engine(
        _database_url(new_location.folder_path, next_config.database_file)
    )
    try:
        create_workspace_database(new_engine)
    finally:
        new_engine.dispose()
    write_storage_config(get_settings().storage_config_path, next_config)
    return _storage_response(next_config)


@router.patch("/storage/active", response_model=StorageSwitchRead)
def switch_storage(
    payload: StorageSwitchRequest,
    session: SessionDep,
    _: CurrentUser,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> StorageSwitchRead:
    config = _read_storage_config()
    location = next((item for item in config.locations if item.id == payload.location_id), None)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    token = session.get(SessionToken, session_token)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    token.workspace_id = location.id
    session.commit()
    return StorageSwitchRead(
        storage=_storage_response(config, active_location=location.id),
        session_ended=False,
    )
