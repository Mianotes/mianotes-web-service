from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Note, NoteStar
from mianotes_web_service.domain.schemas import NoteListItem, SearchResult
from mianotes_web_service.services.paths import note_file_path
from mianotes_web_service.services.search import search_markdown_files

router = APIRouter(prefix="/search", tags=["search"])


def _notes_by_path(session: Session) -> dict[str, Note]:
    notes = session.scalars(select(Note).options(joinedload(Note.folder))).all()
    by_path: dict[str, Note] = {}
    for note in notes:
        note_path = _resolved_note_path(note)
        if note_path is not None:
            by_path[note_path] = note
    return by_path


def _resolved_note_path(note: Note) -> str | None:
    try:
        return str(note_file_path(note).resolve())
    except OSError:
        return None


def _is_starred_by_user(session: Session, note_id: str, user_id: str) -> bool:
    return session.scalars(
        select(NoteStar.note_id).where(NoteStar.note_id == note_id, NoteStar.user_id == user_id)
    ).first() is not None


def _note_list_item(note: Note, *, is_starred: bool) -> NoteListItem:
    return NoteListItem(
        id=note.id,
        user_id=note.user_id,
        folder_id=note.folder_id,
        title=note.title,
        status=note.status,
        source_type=note.source_type,
        revision_number=note.revision_number,
        is_published=note.is_published,
        is_starred=is_starred,
        summary=note.summary,
        filename=note.filename,
        note_path=str(note_file_path(note)),
        created_at=note.created_at,
        updated_at=note.updated_at,
        comments_count=len([comment for comment in note.comments if comment.body]),
        tags=note.tags,
    )


@router.get("", response_model=list[SearchResult])
def search_notes(
    session: SessionDep,
    user: NotesReadUser,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[SearchResult]:
    try:
        matches = search_markdown_files(get_settings().data_dir, q, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    notes_by_path = _notes_by_path(session)
    results: list[SearchResult] = []
    for match in matches:
        note = notes_by_path.get(str(match.path))
        if note is None:
            continue
        results.append(
            SearchResult(
                note=_note_list_item(
                    note,
                    is_starred=_is_starred_by_user(session, note.id, user.id),
                ),
                line_number=match.line_number,
                column=match.column,
                excerpt=match.excerpt,
            )
        )
    return results
