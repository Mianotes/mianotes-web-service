from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from mianotes_web_service.api.dependencies import CurrentUser
from mianotes_web_service.core.config import get_settings

router = APIRouter(prefix="/data", tags=["files"])


@router.get("/{file_path:path}", name="get_data_file")
def get_data_file(file_path: str, user: CurrentUser) -> FileResponse:
    data_dir = get_settings().data_dir.resolve()
    target = (data_dir / file_path).resolve()
    if data_dir not in target.parents and target != data_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(target)
