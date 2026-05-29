from __future__ import annotations

import secrets
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import NotesWriteUser
from mianotes_web_service.api.note_access import ensure_can_change_note, read_note_or_404
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.session import get_session
from mianotes_web_service.services.note_responses import file_url
from mianotes_web_service.services.paths import note_image_directory
from mianotes_web_service.services.storage import slugify
from mianotes_web_service.services.workspace_context import session_data_dir

router = APIRouter(prefix="/notes", tags=["notes"])
SessionDep = Annotated[Session, Depends(get_session)]
SUPPORTED_EDITOR_IMAGE_EXTENSIONS = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
}
EDITOR_IMAGE_EXTENSION_BY_CONTENT_TYPE = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@router.post("/{note_id}/images", status_code=status.HTTP_201_CREATED)
def upload_note_image(
    note_id: str,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
    image: Annotated[UploadFile, File()],
) -> dict[str, str]:
    note = read_note_or_404(session, note_id)
    ensure_can_change_note(note, user)
    if not image.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Image required",
        )

    content_type = (image.content_type or "").split(";", 1)[0].strip().lower()
    extension = Path(image.filename).suffix.lower()
    if extension == ".jpeg":
        extension = ".jpg"
    if extension not in SUPPORTED_EDITOR_IMAGE_EXTENSIONS:
        extension = EDITOR_IMAGE_EXTENSION_BY_CONTENT_TYPE.get(content_type, extension)
    if extension not in SUPPORTED_EDITOR_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image type",
        )

    data_dir = session_data_dir(session, get_settings().data_dir)
    directory = note_image_directory(note, data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = slugify(Path(image.filename).stem, "image")[:80]
    target = directory / f"{stem}-{secrets.token_hex(4)}{extension}"
    with target.open("wb") as output:
        shutil.copyfileobj(image.file, output)
    return {"url": file_url(request, target, data_dir)}
