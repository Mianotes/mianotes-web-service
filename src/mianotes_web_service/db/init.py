from __future__ import annotations

from sqlalchemy.engine import Engine

from mianotes_web_service.services.workspace_context import WorkspaceContext

from .migrations import (
    run_all_migrations,
    run_system_migrations,
    run_workspace_migrations,
)
from .workspace_routing import (
    default_workspace,
    storage_config,
    system_engine,
    workspace_engine,
)


def create_system_database(target_engine: Engine | None = None) -> None:
    run_system_migrations(target_engine or system_engine())


def create_workspace_database(target_engine: Engine | None = None) -> None:
    engine = target_engine or workspace_engine(default_workspace())
    run_workspace_migrations(engine)


def create_database(target_engine: Engine | None = None) -> None:
    if target_engine is not None:
        run_all_migrations(target_engine)
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
