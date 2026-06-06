from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import ShareWriteUser, SessionDep
from mianotes_web_service.api.note_access import (
    ensure_can_change_note,
    read_note_for_change,
    read_note_reference,
    read_shared_note_for_avatar,
    read_shared_note_for_response,
    read_shared_note_for_source_file,
)
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.workspace_routing import (
    sessionmaker_for_workspace,
    workspace_by_id,
)
from mianotes_web_service.domain.schemas import NoteRead
from mianotes_web_service.services.note_responses import note_response
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.share import (
    generate_share_token,
    get_share_secret,
    hash_share_token,
)
from mianotes_web_service.services.storage_settings import DEFAULT_LOCATION_ID
from mianotes_web_service.services.workspace_context import (
    WorkspaceContext,
    reset_current_workspace,
    session_workspace,
    set_current_workspace,
)

router = APIRouter(prefix="/notes", tags=["notes"])


def _session_for_shared_workspace(
    workspace: WorkspaceContext,
    request: Request,
) -> Session:
    testing_session_factory = getattr(request.app.state, "testing_session_factory", None)
    if testing_session_factory is not None and workspace.id == DEFAULT_LOCATION_ID:
        session = testing_session_factory()
    else:
        session = sessionmaker_for_workspace(workspace)()
    session.info["workspace"] = workspace
    return session


@contextmanager
def _shared_workspace_session(
    workspace_id: str,
    request: Request,
) -> Generator[Session, None, None]:
    workspace = workspace_by_id(workspace_id)
    context_token = set_current_workspace(workspace)
    session = _session_for_shared_workspace(workspace, request)
    try:
        yield session
    finally:
        session.close()
        reset_current_workspace(context_token)


@router.get(
    "/shared/workspaces/{workspace_id}/{token}",
    response_model=NoteRead,
    name="get_shared_note",
)
def get_shared_note(workspace_id: str, token: str, request: Request) -> NoteRead:
    with _shared_workspace_session(workspace_id, request) as session:
        note = read_shared_note_for_response(session, token)
        return note_response(note, request, share_token=token, session=session)


@router.get("/shared/{token}", response_model=NoteRead, name="get_legacy_shared_note")
def get_legacy_shared_note(token: str, request: Request) -> NoteRead:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Shared note not found",
    )


@router.get("/shared/workspaces/{workspace_id}/{token}/avatar", name="get_shared_avatar")
def get_shared_avatar(workspace_id: str, token: str, request: Request) -> FileResponse:
    with _shared_workspace_session(workspace_id, request) as session:
        note = read_shared_note_for_avatar(session, token)
        if note.user is None or not note.user.avatar_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        data_dir = get_settings().data_dir.resolve()
        target = (data_dir / note.user.avatar_path).resolve()
        if data_dir not in target.parents and target != data_dir:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if not target.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        return FileResponse(target)


@router.get(
    "/shared/workspaces/{workspace_id}/{token}/files/{source_file_id}",
    name="get_shared_source_file",
)
def get_shared_source_file(
    workspace_id: str,
    token: str,
    source_file_id: str,
    request: Request,
) -> FileResponse:
    with _shared_workspace_session(workspace_id, request) as session:
        note = read_shared_note_for_source_file(session, token)
        source_file = next(
            (candidate for candidate in note.source_files if candidate.id == source_file_id),
            None,
        )
        if source_file is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        target = workspace_paths_for_session(session).source_file_path(source_file)
        if not target.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        return FileResponse(target)


@router.post("/{note_id}/share")
def create_note_share(
    note_id: str,
    session: SessionDep,
    request: Request,
    _user: ShareWriteUser,
) -> dict[str, str]:
    note = read_note_reference(session, note_id)
    secret = get_share_secret(session, create=True)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    token = generate_share_token()
    note.share_token_hash = hash_share_token(secret, token)
    note.shared_at = datetime.now(UTC)
    session.commit()
    workspace = session_workspace(session)
    workspace_id = workspace.id if workspace is not None else DEFAULT_LOCATION_ID
    return {
        "share_url": str(
            request.url_for(
                "get_shared_note",
                workspace_id=workspace_id,
                token=token,
            )
        )
    }


@router.delete("/{note_id}/share", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_share(note_id: str, session: SessionDep, user: ShareWriteUser) -> None:
    note = read_note_for_change(session, note_id)
    ensure_can_change_note(note, user)
    note.share_token_hash = None
    note.shared_at = None
    session.commit()
