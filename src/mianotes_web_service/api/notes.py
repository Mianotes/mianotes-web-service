from __future__ import annotations

import base64
import json
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
from sqlalchemy import Select, and_, delete, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from mianotes_web_service.api.dependencies import (
    NotesReadUser,
    NotesWriteUser,
    TagsWriteUser,
)
from mianotes_web_service.api.note_access import (
    ensure_can_change_note,
    read_note_for_change,
    read_note_for_delete,
    read_note_for_response,
    read_note_for_tag_change,
    read_note_reference,
)
from mianotes_web_service.db.models import Folder, MiaJob, Note, NoteStar, Tag, User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import (
    NoteListPage,
    NoteRead,
    NoteStarUpdate,
    NoteUpdate,
    TagsUpdate,
)
from mianotes_web_service.services.filesystem_uow import (
    FilesystemUnitOfWork,
    commit_with_filesystem_rollback,
)
from mianotes_web_service.services.mia import prompt_markdown
from mianotes_web_service.services.note_deletion import stage_note_files_for_delete
from mianotes_web_service.services.note_moves import move_note_to_folder
from mianotes_web_service.services.note_responses import (
    note_is_starred,
    note_list_response,
    note_response,
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
DEFAULT_NOTES_LIMIT = 20
MAX_NOTES_LIMIT = 100


def _encode_note_cursor(note: Note) -> str:
    payload = {"created_at": note.created_at.isoformat(), "id": note.id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _decode_note_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
        created_at = datetime.fromisoformat(payload["created_at"])
        note_id = str(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid notes cursor",
        ) from exc
    return created_at, note_id


def _note_filter_clauses(
    *,
    user: User,
    user_id: str | None,
    folder_id: str | None,
    starred: bool | None,
    tag: str | None,
    query: str | None,
):
    clauses = []
    if user_id is not None:
        clauses.append(Note.user_id == user_id)
    if folder_id is not None:
        clauses.append(Note.folder_id == folder_id)

    star_exists = exists().where(NoteStar.note_id == Note.id, NoteStar.user_id == user.id)
    if starred is True:
        clauses.append(star_exists)
    elif starred is False:
        clauses.append(~star_exists)

    if tag:
        clauses.append(Note.tags.any(Tag.slug == tag))

    search_term = (query or "").strip().lower()
    if search_term:
        pattern = f"%{search_term}%"
        clauses.append(
            or_(
                func.lower(Note.title).like(pattern),
                func.lower(Note.summary).like(pattern),
                Note.user.has(func.lower(User.name).like(pattern)),
                Note.folder.has(func.lower(Folder.name).like(pattern)),
                Note.tags.any(
                    or_(
                        func.lower(Tag.name).like(pattern),
                        func.lower(Tag.slug).like(pattern),
                    )
                ),
            )
        )
    return clauses


def _apply_note_filters(statement: Select[tuple[Note]], clauses) -> Select[tuple[Note]]:
    for clause in clauses:
        statement = statement.where(clause)
    return statement


def _latest_job_by_note(session: Session, note_ids: list[str]) -> dict[str, MiaJob]:
    if not note_ids:
        return {}
    jobs = session.scalars(
        select(MiaJob)
        .where(MiaJob.note_id.in_(note_ids))
        .order_by(MiaJob.note_id.asc(), MiaJob.created_at.desc(), MiaJob.id.desc())
    )
    latest: dict[str, MiaJob] = {}
    for job in jobs:
        if job.note_id and job.note_id not in latest:
            latest[job.note_id] = job
    return latest


def _folder_note_counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(Note.folder_id, func.count(Note.id)).group_by(Note.folder_id))
    return {folder_id: count for folder_id, count in rows if folder_id is not None}


@router.get("", response_model=NoteListPage)
def list_notes(
    session: SessionDep,
    user: NotesReadUser,
    user_id: Annotated[str | None, Query()] = None,
    folder_id: Annotated[str | None, Query()] = None,
    starred: Annotated[bool | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
    query: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_NOTES_LIMIT)] = DEFAULT_NOTES_LIMIT,
    include_total: Annotated[bool, Query()] = False,
    include_counts: Annotated[bool, Query()] = False,
) -> NoteListPage:
    filter_clauses = _note_filter_clauses(
        user=user,
        user_id=user_id,
        folder_id=folder_id,
        starred=starred,
        tag=tag,
        query=query,
    )
    total = None
    if include_total:
        total_statement = select(func.count()).select_from(Note)
        for clause in filter_clauses:
            total_statement = total_statement.where(clause)
        total = session.scalar(total_statement) or 0

    statement = _apply_note_filters(
        select(Note)
        .options(
            selectinload(Note.folder),
            selectinload(Note.source_files),
            selectinload(Note.tags),
        )
        .order_by(Note.created_at.desc(), Note.id.desc()),
        filter_clauses,
    )
    if cursor:
        cursor_created_at, cursor_id = _decode_note_cursor(cursor)
        statement = statement.where(
            or_(
                Note.created_at < cursor_created_at,
                and_(Note.created_at == cursor_created_at, Note.id < cursor_id),
            )
        )
    notes = list(session.scalars(statement.limit(limit + 1)))
    has_next_page = len(notes) > limit
    page_notes = notes[:limit]
    note_ids = [note.id for note in page_notes]
    starred_ids = starred_note_ids(session, note_ids, user.id)
    latest_jobs = _latest_job_by_note(session, note_ids)
    items = [
        note_list_response(
            note,
            is_starred=note.id in starred_ids,
            session=session,
            latest_job=latest_jobs.get(note.id),
        )
        for note in page_notes
    ]
    return NoteListPage(
        items=items,
        total=total,
        limit=limit,
        next_cursor=_encode_note_cursor(page_notes[-1]) if has_next_page and page_notes else None,
        counts={"folders": _folder_note_counts(session)} if include_counts else None,
    )


@router.get("/{note_id}", response_model=NoteRead)
def get_note(
    note_id: str,
    session: SessionDep,
    request: Request,
    user: NotesReadUser,
) -> NoteRead:
    return note_response(
        read_note_for_response(session, note_id),
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
    note = read_note_for_tag_change(session, note_id)
    ensure_can_change_note(note, user)
    sync_note_tags(session, note, payload.tags)
    session.commit()
    return note_response(
        read_note_for_response(session, note.id),
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
    note = read_note_reference(session, note_id)
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
        read_note_for_response(session, note.id),
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
    note = (
        read_note_for_tag_change(session, note_id)
        if payload.tags is not None
        else read_note_for_change(session, note_id)
    )
    ensure_can_change_note(note, user)
    filesystem = FilesystemUnitOfWork()

    if payload.folder_id is not None:
        folder = session.get(Folder, payload.folder_id)
        if folder is None or folder.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        paths = workspace_paths_for_session(session)
        move_note_to_folder(
            note,
            folder,
            data_dir=paths.data_dir,
            filesystem=filesystem,
        )
    else:
        paths = workspace_paths_for_session(session)

    next_title = payload.title or note.title
    note_path = paths.note_file_path(note)
    is_manual_content_edit = payload.text is not None or payload.title is not None
    if payload.text is not None:
        filesystem.replace_text(
            note_path,
            render_markdown_note(title=next_title, text=payload.text),
            encoding="utf-8",
        )
        note.summary = summarize_text(payload.text)
        note.revision_number += 1
    elif payload.title is not None:
        filesystem.replace_text(
            note_path,
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
    commit_with_filesystem_rollback(session, filesystem)
    return note_response(
        read_note_for_response(session, note.id),
        request,
        is_starred=note_is_starred(session, note.id, user.id),
        session=session,
    )


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, session: SessionDep, user: NotesWriteUser) -> None:
    note = read_note_for_delete(session, note_id)
    ensure_can_change_note(note, user)
    filesystem = FilesystemUnitOfWork()
    stage_note_files_for_delete(note, workspace_paths_for_session(session), filesystem)
    session.delete(note)
    commit_with_filesystem_rollback(session, filesystem)
