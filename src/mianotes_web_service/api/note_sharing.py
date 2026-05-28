from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import ShareWriteUser
from mianotes_web_service.api.note_access import (
    ensure_can_change_note,
    read_note_by_share_token,
    read_note_or_404,
)
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Note
from mianotes_web_service.db.session import (
    _storage_config,
    get_session,
    sessionmaker_for_workspace,
)
from mianotes_web_service.domain.schemas import NoteRead
from mianotes_web_service.services.note_responses import note_response
from mianotes_web_service.services.paths import source_file_path
from mianotes_web_service.services.share import (
    generate_share_token,
    get_share_secret,
    hash_share_token,
)
from mianotes_web_service.services.workspace_context import (
    WorkspaceContext,
    reset_current_workspace,
    set_current_workspace,
)

router = APIRouter(prefix="/notes", tags=["notes"])
SessionDep = Annotated[Session, Depends(get_session)]
SharedResult = TypeVar("SharedResult")


def _configured_workspaces() -> list[WorkspaceContext]:
    config = _storage_config()
    return [
        WorkspaceContext(
            id=location.id,
            name=location.name,
            folder_path=location.folder_path,
            database_file=config.database_file,
        )
        for location in config.locations
    ]


def _with_shared_note(
    token: str,
    handler: Callable[[Note, Session], SharedResult],
    *,
    request: Request | None = None,
) -> SharedResult:
    testing_session_factory = (
        getattr(request.app.state, "testing_session_factory", None) if request else None
    )
    if testing_session_factory is not None:
        with testing_session_factory() as session:
            note = read_note_by_share_token(session, token)
            return handler(note, session)

    for workspace in _configured_workspaces():
        context_token = set_current_workspace(workspace)
        try:
            with sessionmaker_for_workspace(workspace)() as session:
                try:
                    note = read_note_by_share_token(session, token)
                except HTTPException as exc:
                    if exc.status_code == status.HTTP_404_NOT_FOUND:
                        continue
                    raise
                return handler(note, session)
        finally:
            reset_current_workspace(context_token)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared note not found")


@router.get("/shared/{token}", response_model=NoteRead, name="get_shared_note")
def get_shared_note(token: str, request: Request) -> NoteRead:
    return _with_shared_note(
        token,
        lambda note, _session: note_response(note, request, share_token=token),
        request=request,
    )


@router.get("/shared/{token}/avatar", name="get_shared_avatar")
def get_shared_avatar(token: str, request: Request) -> FileResponse:
    def response(note: Note, _session: Session) -> FileResponse:
        if note.user is None or not note.user.avatar_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        data_dir = get_settings().data_dir.resolve()
        target = (data_dir / note.user.avatar_path).resolve()
        if data_dir not in target.parents and target != data_dir:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if not target.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        return FileResponse(target)

    return _with_shared_note(token, response, request=request)


@router.get("/shared/{token}/files/{source_file_id}", name="get_shared_source_file")
def get_shared_source_file(
    token: str,
    source_file_id: str,
    request: Request,
) -> FileResponse:
    def response(note: Note, _session: Session) -> FileResponse:
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

    return _with_shared_note(token, response, request=request)


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
