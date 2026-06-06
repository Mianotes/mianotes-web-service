from __future__ import annotations

import secrets
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from mianotes_web_service.api.dependencies import NotesWriteUser, SessionDep
from mianotes_web_service.services.note_repository import ensure_can_change_note, read_note_for_change
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.services.note_responses import workspace_note_image_url
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.storage import slugify
from mianotes_web_service.services.upload_limits import (
    ImageTooLargeError,
    UploadTooLargeError,
    ensure_image_pixel_limit,
    read_stream_with_limit,
)

router = APIRouter(prefix="/notes", tags=["notes"])
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
    user: NotesWriteUser,
    image: Annotated[UploadFile, File()],
) -> dict[str, str]:
    note = read_note_for_change(session, note_id)
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
    settings = get_settings()
    try:
        image_bytes = read_stream_with_limit(
            image.file,
            max_bytes=settings.max_editor_image_bytes,
        )
        with Image.open(BytesIO(image_bytes)) as opened_image:
            ensure_image_pixel_limit(
                opened_image.width,
                opened_image.height,
                max_pixels=settings.max_image_pixels,
            )
            opened_image.verify()
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Image is too large. Maximum image upload size is {exc.max_bytes} bytes.",
        ) from exc
    except ImageTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Image is too large. Maximum image size is {exc.max_pixels} pixels.",
        ) from exc
    except UnidentifiedImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read this image",
        ) from exc

    paths = workspace_paths_for_session(session)
    directory = paths.note_image_directory(note)
    directory.mkdir(parents=True, exist_ok=True)
    stem = slugify(Path(image.filename).stem, "image")[:80]
    target = directory / f"{stem}-{secrets.token_hex(4)}{extension}"
    target.write_bytes(image_bytes)
    return {"url": workspace_note_image_url(note, target.name, session)}
