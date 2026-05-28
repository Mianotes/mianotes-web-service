from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from mianotes_web_service.services.workspace_context import WorkspaceContext

from .models import (
    ApiToken,
    AppSetting,
    Base,
    Comment,
    Folder,
    MiaJob,
    Note,
    NoteStar,
    NoteTag,
    PublishedSite,
    SessionToken,
    SourceFile,
    Tag,
    User,
)
from .session import (
    default_workspace,
    system_engine,
    workspace_engine,
)

SYSTEM_TABLES = (
    User.__table__,
    SessionToken.__table__,
    ApiToken.__table__,
    AppSetting.__table__,
)
WORKSPACE_TABLES = (
    Folder.__table__,
    Note.__table__,
    PublishedSite.__table__,
    SourceFile.__table__,
    Comment.__table__,
    Tag.__table__,
    NoteTag.__table__,
    NoteStar.__table__,
    MiaJob.__table__,
)


def _add_missing_columns(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    if "users" in tables:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        with target_engine.begin() as connection:
            if "password_hash" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT"))
    if "session_tokens" in tables:
        session_columns = {column["name"] for column in inspector.get_columns("session_tokens")}
        with target_engine.begin() as connection:
            if "workspace_id" not in session_columns:
                connection.execute(
                    text("ALTER TABLE session_tokens ADD COLUMN workspace_id VARCHAR(120)")
                )
    if "mia_jobs" in tables:
        job_columns = {column["name"] for column in inspector.get_columns("mia_jobs")}
        with target_engine.begin() as connection:
            if "client_key" not in job_columns:
                connection.execute(text("ALTER TABLE mia_jobs ADD COLUMN client_key VARCHAR(80)"))
            if "client_name" not in job_columns:
                connection.execute(text("ALTER TABLE mia_jobs ADD COLUMN client_name VARCHAR(120)"))


def create_system_database(target_engine: Engine = system_engine) -> None:
    Base.metadata.create_all(bind=target_engine, tables=SYSTEM_TABLES)
    _add_missing_columns(target_engine)


def create_workspace_database(target_engine: Engine | None = None) -> None:
    engine = target_engine or workspace_engine(default_workspace())
    Base.metadata.create_all(bind=engine, tables=WORKSPACE_TABLES)
    _add_missing_columns(engine)


def create_database(target_engine: Engine | None = None) -> None:
    if target_engine is not None:
        Base.metadata.create_all(bind=target_engine)
        _add_missing_columns(target_engine)
        return
    create_system_database()
    create_all_configured_workspace_databases()


def create_all_configured_workspace_databases() -> None:
    from .session import _storage_config

    config = _storage_config()
    default = default_workspace()
    for location in config.locations:
        workspace = default
        if location.id != default.id:
            workspace = WorkspaceContext(
                id=location.id,
                name=location.name,
                folder_path=location.folder_path,
                database_file=config.database_file,
            )
        create_workspace_database(workspace_engine(workspace))
