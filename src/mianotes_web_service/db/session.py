from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Header, HTTPException, Request, status
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import (
    ApiToken,
    AppSetting,
    SessionToken,
    User,
)
from mianotes_web_service.services.auth import SESSION_COOKIE_NAME
from mianotes_web_service.services.storage_settings import (
    StorageConfig,
    StorageLocation,
    read_storage_config,
    storage_database_path,
    system_database_path,
)
from mianotes_web_service.services.workspace_context import (
    WorkspaceContext,
    reset_current_workspace,
    set_current_workspace,
)

SYSTEM_MODELS = (User, SessionToken, ApiToken, AppSetting)


def _connect_args(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _prepare_sqlite_database(database_url: str) -> None:
    if not database_url.startswith("sqlite") or database_url.endswith(":memory:"):
        return
    if ":///" not in database_url:
        return
    path = Path(database_url.split(":///", 1)[1])
    path.parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: str) -> Engine:
    _prepare_sqlite_database(database_url)
    return create_engine(database_url, connect_args=_connect_args(database_url))


settings = get_settings()
system_engine = create_database_engine(f"sqlite:///{system_database_path(settings.data_dir)}")
SystemSessionLocal = sessionmaker(
    bind=system_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

_workspace_engines: dict[str, Engine] = {}


def _storage_config() -> StorageConfig:
    settings = get_settings()
    return read_storage_config(settings.storage_config_path, default_data_dir=settings.data_dir)


def _workspace_for_location(location: StorageLocation, database_file: str) -> WorkspaceContext:
    return WorkspaceContext(
        id=location.id,
        name=location.name,
        folder_path=location.folder_path,
        database_file=database_file,
    )


def default_workspace() -> WorkspaceContext:
    config = _storage_config()
    return _workspace_for_location(
        next(
            (location for location in config.locations if location.id == config.active_location),
            config.locations[0],
        ),
        config.database_file,
    )


def workspace_by_id(workspace_id: str) -> WorkspaceContext:
    config = _storage_config()
    location = next((item for item in config.locations if item.id == workspace_id), None)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    return _workspace_for_location(location, config.database_file)


def _workspace_database_url(workspace: WorkspaceContext) -> str:
    return f"sqlite:///{storage_database_path(workspace.folder_path, workspace.database_file)}"


def workspace_engine(workspace: WorkspaceContext) -> Engine:
    database_url = _workspace_database_url(workspace)
    cached = _workspace_engines.get(database_url)
    if cached is not None:
        return cached
    engine = create_database_engine(database_url)
    _workspace_engines[database_url] = engine
    return engine


def sessionmaker_for_workspace(workspace: WorkspaceContext) -> sessionmaker[Session]:
    return sessionmaker(
        bind=workspace_engine(workspace),
        binds={model: system_engine for model in SYSTEM_MODELS},
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


SessionLocal = sessionmaker_for_workspace(default_workspace())


def _workspace_from_session_token(session_token: str | None) -> str | None:
    if not session_token:
        return None
    with SystemSessionLocal() as session:
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
    session_workspace_id = _workspace_from_session_token(session_token)
    if session_workspace_id:
        return workspace_by_id(session_workspace_id)
    return default_workspace()


def reconfigure_database(database_url: str) -> Engine:
    """Compatibility shim for older storage-switch code paths."""

    return create_database_engine(database_url)


def get_system_session() -> Generator[Session, None, None]:
    session = SystemSessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_session(
    request: Request,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    x_mianotes_workspace: Annotated[str | None, Header(alias="X-Mianotes-Workspace")] = None,
) -> Generator[Session, None, None]:
    workspace = resolve_workspace(
        session_token=session_token,
        workspace_header=x_mianotes_workspace,
    )
    session_factory = sessionmaker_for_workspace(workspace)
    session = session_factory()
    session.info["workspace"] = workspace
    token = set_current_workspace(workspace)
    try:
        yield session
    finally:
        session.close()
        reset_current_workspace(token)
