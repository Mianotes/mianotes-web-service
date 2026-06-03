from __future__ import annotations

from fastapi import APIRouter

from .auth import router as auth_router
from .context import router as context_router
from .files import router as files_router
from .folders import router as folders_router
from .jobs import router as jobs_router
from .note_images import router as note_images_router
from .note_ingestion import router as note_ingestion_router
from .note_prompts import router as note_prompts_router
from .note_sharing import router as note_sharing_router
from .notes import router as notes_router
from .publish import router as publish_router
from .search import router as search_router
from .settings import router as settings_router
from .storage import router as storage_router
from .tags import router as tags_router
from .tokens import router as tokens_router
from .users import router as users_router
from .v1 import router as v1_router

api_router = APIRouter()
api_router.include_router(v1_router, prefix="/api")
api_router.include_router(auth_router, prefix="/api")
api_router.include_router(users_router, prefix="/api")
api_router.include_router(folders_router, prefix="/api")
api_router.include_router(storage_router, prefix="/api")
api_router.include_router(settings_router, prefix="/api")
api_router.include_router(tags_router, prefix="/api")
api_router.include_router(tokens_router, prefix="/api")
api_router.include_router(jobs_router, prefix="/api")
api_router.include_router(note_ingestion_router, prefix="/api")
api_router.include_router(note_images_router, prefix="/api")
api_router.include_router(note_sharing_router, prefix="/api")
api_router.include_router(note_prompts_router, prefix="/api")
api_router.include_router(notes_router, prefix="/api")
api_router.include_router(search_router, prefix="/api")
api_router.include_router(context_router, prefix="/api")
api_router.include_router(publish_router, prefix="/api")
api_router.include_router(files_router)
