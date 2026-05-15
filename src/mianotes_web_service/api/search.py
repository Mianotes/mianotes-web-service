from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Note
from mianotes_web_service.domain.schemas import NoteListItem, SearchResult
from mianotes_web_service.services.search import search_markdown_files

router = APIRouter(prefix="/search", tags=["search"])


def _notes_by_path(session: Session) -> dict[str, Note]:
    notes = session.scalars(select(Note)).all()
    by_path: dict[str, Note] = {}
    for note in notes:
        note_path = _resolved_note_path(note)
        if note_path is not None:
            by_path[note_path] = note
    return by_path


def _resolved_note_path(note: Note) -> str | None:
    try:
        return str(Path(note.note_path).resolve())
    except OSError:
        return None


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
                note=NoteListItem.model_validate(note),
                line_number=match.line_number,
                column=match.column,
                excerpt=match.excerpt,
            )
        )
    return results
