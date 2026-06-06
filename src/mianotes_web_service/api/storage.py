from __future__ import annotations

from fastapi import APIRouter

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.domain.schemas import StorageCapacityRead
from mianotes_web_service.services.storage_capacity import get_storage_capacity
from mianotes_web_service.services.workspace_context import current_data_dir

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("", response_model=StorageCapacityRead)
def read_storage_capacity(session: SessionDep, user: NotesReadUser) -> dict[str, object]:
    return get_storage_capacity(session, current_data_dir(get_settings().data_dir))
