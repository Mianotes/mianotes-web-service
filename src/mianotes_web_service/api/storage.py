from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import NotesReadUser
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import StorageCapacityRead
from mianotes_web_service.services.storage_capacity import get_storage_capacity
from mianotes_web_service.services.workspace_context import current_data_dir

router = APIRouter(prefix="/storage", tags=["storage"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=StorageCapacityRead)
def read_storage_capacity(session: SessionDep, user: NotesReadUser) -> dict[str, object]:
    return get_storage_capacity(session, current_data_dir(get_settings().data_dir))
