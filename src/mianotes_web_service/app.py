from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .api.routes import api_router
from .db.init import create_all_configured_workspace_databases, create_system_database
from .db.workspace_routing import sessionmaker_for_workspace, storage_config
from .services.job_runner import InProcessJobRunner, fail_interrupted_jobs
from .services.workspace_context import (
    WorkspaceContext,
    reset_current_workspace,
    set_current_workspace,
)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        create_system_database()
        create_all_configured_workspace_databases()
        config = storage_config()
        for location in config.locations:
            workspace = WorkspaceContext(
                id=location.id,
                name=location.name,
                folder_path=location.folder_path,
                database_file=config.database_file,
            )
            token = set_current_workspace(workspace)
            try:
                with sessionmaker_for_workspace(workspace)() as session:
                    fail_interrupted_jobs(session)
            finally:
                reset_current_workspace(token)
        yield

    app = FastAPI(
        title="Mianotes Web Service",
        version=__version__,
        description="Filesystem-first AI note generation API for Mianotes.",
        lifespan=lifespan,
    )
    app.state.job_runner = InProcessJobRunner(sessionmaker_for_workspace)
    app.include_router(api_router)
    return app
