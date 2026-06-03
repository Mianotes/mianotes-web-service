from __future__ import annotations

from sqlalchemy.engine import Engine

from mianotes_web_service.services.workspace_context import WorkspaceContext

from .schema import SYSTEM_TABLES, WORKSPACE_TABLES, create_tables
from .workspace_routing import (
    default_workspace,
    storage_config,
    system_engine,
    workspace_engine,
)


def create_system_database(target_engine: Engine | None = None) -> None:
    create_tables(target_engine or system_engine(), SYSTEM_TABLES)


def create_workspace_database(target_engine: Engine | None = None) -> None:
    engine = target_engine or workspace_engine(default_workspace())
    create_tables(engine, WORKSPACE_TABLES)


def create_database(target_engine: Engine | None = None) -> None:
    if target_engine is not None:
        create_tables(target_engine, (*SYSTEM_TABLES, *WORKSPACE_TABLES))
        return
    create_system_database()
    create_all_configured_workspace_databases()


def create_all_configured_workspace_databases() -> None:
    config = storage_config()
    default = default_workspace()
    for location in config.locations:
        workspace = default
        if location.id != default.id:
            workspace = WorkspaceContext(
                id=location.id,
                name=location.name,
                folder_path=location.folder_path,
            )
        create_workspace_database(workspace_engine(workspace))
