from __future__ import annotations

from fastapi import FastAPI

from . import __version__
from .api.routes import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mianotes Web Service",
        version=__version__,
        description="Filesystem-first AI note generation API for Mianotes.",
    )
    app.include_router(api_router)
    return app

