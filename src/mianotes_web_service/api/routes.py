from __future__ import annotations

from fastapi import APIRouter

from .auth import router as auth_router
from .files import router as files_router
from .jobs import router as jobs_router
from .notes import router as notes_router
from .projects import router as projects_router
from .search import router as search_router
from .tags import router as tags_router
from .tokens import router as tokens_router
from .users import router as users_router
from .v1 import router as v1_router

api_router = APIRouter()
api_router.include_router(v1_router, prefix="/api")
api_router.include_router(auth_router, prefix="/api")
api_router.include_router(users_router, prefix="/api")
api_router.include_router(projects_router, prefix="/api")
api_router.include_router(tags_router, prefix="/api")
api_router.include_router(tokens_router, prefix="/api")
api_router.include_router(jobs_router, prefix="/api")
api_router.include_router(notes_router, prefix="/api")
api_router.include_router(search_router, prefix="/api")
api_router.include_router(files_router)
