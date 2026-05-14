from __future__ import annotations

from fastapi import APIRouter

from .topics import router as topics_router
from .users import router as users_router
from .v1 import router as v1_router

api_router = APIRouter()
api_router.include_router(v1_router, prefix="/api")
api_router.include_router(users_router, prefix="/api")
api_router.include_router(topics_router, prefix="/api")
