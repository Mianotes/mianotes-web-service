from __future__ import annotations

from fastapi import APIRouter

from mianotes_web_service import __version__
from mianotes_web_service.core.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "mianotes-web-service",
        "version": __version__,
        "storage": {
            "data_dir": str(settings.data_dir),
            "database_url": settings.redacted_database_url,
        },
    }

