from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .api.routes import api_router
from .db.session import SessionLocal
from .services.job_runner import InProcessJobRunner, fail_interrupted_jobs


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        with SessionLocal() as session:
            fail_interrupted_jobs(session)
        yield

    app = FastAPI(
        title="Mianotes Web Service",
        version=__version__,
        description="Filesystem-first AI note generation API for Mianotes.",
        lifespan=lifespan,
    )
    app.state.job_runner = InProcessJobRunner(SessionLocal)
    app.include_router(api_router)
    return app
