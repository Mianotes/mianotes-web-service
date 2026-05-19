from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from mianotes_web_service.api.dependencies import NotesReadUser
from mianotes_web_service.core.config import get_settings

router = APIRouter(tags=["files"])
PRIVATE_DATA_FILENAMES = {"mia.db", "mia.db-wal", "mia.db-shm", "mia.db-journal"}


def _file_response(file_path: str) -> FileResponse:
    data_dir = get_settings().data_dir.resolve()
    target = (data_dir / file_path).resolve()
    if data_dir not in target.parents and target != data_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if target.name in PRIVATE_DATA_FILENAMES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(target)


@router.get("/{file_path:path}", name="get_project_file")
def get_project_file(file_path: str, user: NotesReadUser) -> FileResponse:
    return _file_response(file_path)
