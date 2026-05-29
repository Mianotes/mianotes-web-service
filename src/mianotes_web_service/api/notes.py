from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.api.dependencies import (
    NotesReadUser,
    NotesWriteUser,
    TagsWriteUser,
)
from mianotes_web_service.api.note_access import (
    ensure_can_change_note,
    read_note_or_404,
)
from mianotes_web_service.db.models import (
    Folder,
    MiaJob,
    Note,
    NoteStar,
)
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import (
    NoteListItem,
    NoteRead,
    NoteStarUpdate,
    NoteUpdate,
    TagsUpdate,
)
from mianotes_web_service.services.mia import prompt_markdown
from mianotes_web_service.services.note_moves import move_note_to_folder
from mianotes_web_service.services.note_responses import (
    note_is_starred,
    note_list_response,
    note_response,
    note_summary_needs_refresh,
    starred_note_ids,
)
from mianotes_web_service.services.note_tags import sync_note_tags
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.storage import (
    render_markdown_note,
    replace_markdown_title,
    summarize_text,
)

router = APIRouter(prefix="/notes", tags=["notes"])
SessionDep = Annotated[Session, Depends(get_session)]
__all__ = ["prompt_markdown", "router"]


@router.get("", response_model=list[NoteListItem])
def list_notes(
    session: SessionDep,
    request: Request,
    user: NotesReadUser,
    user_id: Annotated[str | None, Query()] = None,
    folder_id: Annotated[str | None, Query()] = None,
    starred: Annotated[bool | None, Query()] = None,
) -> list[NoteListItem]:
    statement = (
        select(Note)
        .options(
            joinedload(Note.comments),
            joinedload(Note.folder),
            joinedload(Note.source_files),
            joinedload(Note.tags),
            joinedload(Note.jobs),
        )
        .order_by(Note.created_at.desc())
    )
    if user_id is not None:
        statement = statement.where(Note.user_id == user_id)
    if folder_id is not None:
        statement = statement.where(Note.folder_id == folder_id)
    star_exists = exists().where(NoteStar.note_id == Note.id, NoteStar.user_id == user.id)
    if starred is True:
        statement = statement.where(star_exists)
    elif starred is False:
        statement = statement.where(~star_exists)
    notes = list(session.scalars(statement).unique())
    needs_summary_backfill = any(note_summary_needs_refresh(note) for note in notes)
    starred_ids = starred_note_ids(session, [note.id for note in notes], user.id)
    items = [
        note_list_response(note, request, is_starred=note.id in starred_ids, session=session)
        for note in notes
    ]
    if needs_summary_backfill:
        session.commit()
    return items


@router.get("/{note_id}", response_model=NoteRead)
def get_note(
    note_id: str,
    session: SessionDep,
    request: Request,
    user: NotesReadUser,
) -> NoteRead:
    return note_response(
        read_note_or_404(session, note_id),
        request,
        is_starred=note_is_starred(session, note_id, user.id),
        session=session,
    )


@router.put("/{note_id}/tags", response_model=NoteRead)
def update_note_tags(
    note_id: str,
    payload: TagsUpdate,
    session: SessionDep,
    request: Request,
    user: TagsWriteUser,
) -> NoteRead:
    note = read_note_or_404(session, note_id)
    ensure_can_change_note(note, user)
    sync_note_tags(session, note, payload.tags)
    session.commit()
    return note_response(
        read_note_or_404(session, note.id),
        request,
        is_starred=note_is_starred(session, note.id, user.id),
        session=session,
    )


@router.patch("/{note_id}/star", response_model=NoteRead, name="update_note_star")
def update_note_star(
    note_id: str,
    payload: NoteStarUpdate,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
) -> NoteRead:
    note = read_note_or_404(session, note_id)
    existing_star = session.scalars(
        select(NoteStar).where(NoteStar.note_id == note.id, NoteStar.user_id == user.id)
    ).one_or_none()
    if payload.is_starred and existing_star is None:
        session.add(NoteStar(note_id=note.id, user_id=user.id))
    elif not payload.is_starred and existing_star is not None:
        session.execute(
            delete(NoteStar).where(NoteStar.note_id == note.id, NoteStar.user_id == user.id)
        )
    session.commit()
    return note_response(
        read_note_or_404(session, note.id),
        request,
        is_starred=payload.is_starred,
        session=session,
    )


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    note_id: str,
    payload: NoteUpdate,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
) -> NoteRead:
    note = read_note_or_404(session, note_id)
    ensure_can_change_note(note, user)

    if payload.folder_id is not None:
        folder = session.get(Folder, payload.folder_id)
        if folder is None or folder.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        paths = workspace_paths_for_session(session)
        move_note_to_folder(
            note,
            folder,
            data_dir=paths.data_dir,
        )
    else:
        paths = workspace_paths_for_session(session)

    next_title = payload.title or note.title
    note_path = paths.note_file_path(note)
    is_manual_content_edit = payload.text is not None or payload.title is not None
    if payload.text is not None:
        note_path.write_text(
            render_markdown_note(title=next_title, text=payload.text),
            encoding="utf-8",
        )
        note.summary = summarize_text(payload.text)
        note.revision_number += 1
    elif payload.title is not None:
        note_path.write_text(
            replace_markdown_title(note_path.read_text(encoding="utf-8"), next_title),
            encoding="utf-8",
        )
        note.revision_number += 1
    if note.status == "failed" and is_manual_content_edit:
        note.status = "ready"
        session.execute(
            delete(MiaJob).where(MiaJob.note_id == note.id, MiaJob.status == "failed")
        )
    note.title = next_title
    if payload.is_published is not None:
        note.is_published = payload.is_published
        note.published_at = datetime.now(UTC) if payload.is_published else None
    if payload.tags is not None:
        sync_note_tags(session, note, payload.tags)
    session.commit()
    return note_response(
        read_note_or_404(session, note.id),
        request,
        is_starred=note_is_starred(session, note.id, user.id),
        session=session,
    )


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, session: SessionDep, user: NotesWriteUser) -> None:
    note = read_note_or_404(session, note_id)
    ensure_can_change_note(note, user)
    session.delete(note)
    session.commit()
