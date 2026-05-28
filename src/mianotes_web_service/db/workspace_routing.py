from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.engine import create_database_engine
from mianotes_web_service.db.models import ApiToken, AppSetting, SessionToken, User
from mianotes_web_service.services.storage_settings import (
    StorageConfig,
    StorageLocation,
    read_storage_config,
    storage_database_path,
    system_database_path,
)
from mianotes_web_service.services.workspace_context import WorkspaceContext

SYSTEM_MODELS = (User, SessionToken, ApiToken, AppSetting)

_system_engines: dict[str, Engine] = {}
_workspace_engines: dict[str, Engine] = {}


def storage_config() -> StorageConfig:
    settings = get_settings()
    return read_storage_config(settings.storage_config_path, default_data_dir=settings.data_dir)


def system_database_url() -> str:
    settings = get_settings()
    return f"sqlite:///{system_database_path(settings.data_dir)}"


def system_engine() -> Engine:
    database_url = system_database_url()
    cached = _system_engines.get(database_url)
    if cached is not None:
        return cached
    engine = create_database_engine(database_url)
    _system_engines[database_url] = engine
    return engine


def system_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(
        bind=system_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def workspace_for_location(location: StorageLocation, database_file: str) -> WorkspaceContext:
    return WorkspaceContext(
        id=location.id,
        name=location.name,
        folder_path=location.folder_path,
        database_file=database_file,
    )


def configured_workspaces() -> list[WorkspaceContext]:
    config = storage_config()
    return [
        workspace_for_location(location, config.database_file)
        for location in config.locations
    ]


def default_workspace() -> WorkspaceContext:
    config = storage_config()
    return workspace_for_location(
        next(
            (location for location in config.locations if location.id == config.active_location),
            config.locations[0],
        ),
        config.database_file,
    )


def workspace_by_id(workspace_id: str) -> WorkspaceContext:
    config = storage_config()
    location = next((item for item in config.locations if item.id == workspace_id), None)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    return workspace_for_location(location, config.database_file)


def workspace_database_url(workspace: WorkspaceContext) -> str:
    return f"sqlite:///{storage_database_path(workspace.folder_path, workspace.database_file)}"


def workspace_engine(workspace: WorkspaceContext) -> Engine:
    database_url = workspace_database_url(workspace)
    cached = _workspace_engines.get(database_url)
    if cached is not None:
        return cached
    engine = create_database_engine(database_url)
    _workspace_engines[database_url] = engine
    return engine


def sessionmaker_for_workspace(workspace: WorkspaceContext) -> sessionmaker[Session]:
    return sessionmaker(
        bind=workspace_engine(workspace),
        binds={model: system_engine() for model in SYSTEM_MODELS},
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def workspace_id_from_session_token(session_token: str | None) -> str | None:
    if not session_token:
        return None
    with system_sessionmaker()() as session:
        token = session.get(SessionToken, session_token)
        workspace_id = getattr(token, "workspace_id", None) if token is not None else None
        return workspace_id if isinstance(workspace_id, str) and workspace_id else None


def resolve_workspace(
    *,
    session_token: str | None = None,
    workspace_header: str | None = None,
) -> WorkspaceContext:
    if workspace_header:
        return workspace_by_id(workspace_header)
    session_workspace_id = workspace_id_from_session_token(session_token)
    if session_workspace_id:
        return workspace_by_id(session_workspace_id)
    return default_workspace()
