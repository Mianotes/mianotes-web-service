from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Note, NoteStar
from mianotes_web_service.domain.schemas import NoteListItem, SearchResult
from mianotes_web_service.services.paths import note_file_path, source_file_path
from mianotes_web_service.services.search import search_markdown_files

router = APIRouter(prefix="/search", tags=["search"])


def _notes_by_path(session: Session) -> dict[str, Note]:
    notes = (
        session.scalars(
            select(Note).options(joinedload(Note.folder), joinedload(Note.source_files))
        )
        .unique()
        .all()
    )
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


def _file_url(request: Request, path: str | Path) -> str:
    data_dir = get_settings().data_dir.resolve()
    target = Path(path).resolve()
    try:
        public_path = target.relative_to(data_dir)
    except ValueError:
        public_path = Path(path)
    return str(request.url_for("get_folder_file", file_path=str(public_path)))


def _source_file_list_payload(note: Note, request: Request) -> list[dict[str, object]]:
    return [
        {
            "id": source_file.id,
            "file_path": str(source_file_path(source_file)),
            "original_filename": source_file.original_filename,
            "content_type": source_file.content_type,
            "url": _file_url(request, source_file_path(source_file)),
        }
        for source_file in note.source_files
    ]


def _note_list_item(note: Note, request: Request, *, is_starred: bool) -> NoteListItem:
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
        source_files=_source_file_list_payload(note, request),
        created_at=note.created_at,
        updated_at=note.updated_at,
        comments_count=len([comment for comment in note.comments if comment.body]),
        tags=note.tags,
    )


@router.get("", response_model=list[SearchResult])
def search_notes(
    session: SessionDep,
    request: Request,
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
                    request,
                    is_starred=_is_starred_by_user(session, note.id, user.id),
                ),
                line_number=match.line_number,
                column=match.column,
                excerpt=match.excerpt,
            )
        )
    return results
