from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import ShareWriteUser
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.api.note_access import (
    ensure_can_change_note,
    read_note_by_share_token,
    read_note_or_404,
)
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import NoteRead
from mianotes_web_service.services.note_responses import note_response
from mianotes_web_service.services.paths import source_file_path
from mianotes_web_service.services.share import (
    generate_share_token,
    get_share_secret,
    hash_share_token,
)

router = APIRouter(prefix="/notes", tags=["notes"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/shared/{token}", response_model=NoteRead, name="get_shared_note")
def get_shared_note(token: str, session: SessionDep, request: Request) -> NoteRead:
    note = read_note_by_share_token(session, token)
    return note_response(note, request, share_token=token)


@router.get("/shared/{token}/avatar", name="get_shared_avatar")
def get_shared_avatar(token: str, session: SessionDep) -> FileResponse:
    note = read_note_by_share_token(session, token)
    if note.user is None or not note.user.avatar_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    data_dir = get_settings().data_dir.resolve()
    target = (data_dir / note.user.avatar_path).resolve()
    if data_dir not in target.parents and target != data_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(target)


@router.get("/shared/{token}/files/{source_file_id}", name="get_shared_source_file")
def get_shared_source_file(
    token: str,
    source_file_id: str,
    session: SessionDep,
) -> FileResponse:
    note = read_note_by_share_token(session, token)
    source_file = next(
        (candidate for candidate in note.source_files if candidate.id == source_file_id),
        None,
    )
    if source_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    target = source_file_path(source_file)
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(target)


@router.post("/{note_id}/share")
def create_note_share(
    note_id: str,
    session: SessionDep,
    request: Request,
    user: ShareWriteUser,
) -> dict[str, str]:
    note = read_note_or_404(session, note_id)
    ensure_can_change_note(note, user)
    secret = get_share_secret(session, create=True)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    token = generate_share_token()
    note.share_token_hash = hash_share_token(secret, token)
    note.shared_at = datetime.now(UTC)
    session.commit()
    return {"share_url": str(request.url_for("get_shared_note", token=token))}


@router.delete("/{note_id}/share", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_share(note_id: str, session: SessionDep, user: ShareWriteUser) -> None:
    note = read_note_or_404(session, note_id)
    ensure_can_change_note(note, user)
    note.share_token_hash = None
    note.shared_at = None
    session.commit()
