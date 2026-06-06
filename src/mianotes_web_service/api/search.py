from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.db.models import Note
from mianotes_web_service.domain.schemas import NoteListItem, SearchResult
from mianotes_web_service.services.note_path_lookup import notes_by_matched_path
from mianotes_web_service.services.note_responses import (
    source_file_list_payload,
    starred_note_ids,
)
from mianotes_web_service.services.paths import (
    WorkspacePaths,
    note_file_path,
    workspace_paths_for_session,
)
from mianotes_web_service.services.search import search_markdown_files

router = APIRouter(prefix="/search", tags=["search"])


def _note_list_item(
    note: Note,
    *,
    is_starred: bool,
    paths: WorkspacePaths | None = None,
    session: Session | None = None,
) -> NoteListItem:
    note_path = paths.note_file_path(note) if paths is not None else note_file_path(note)
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
        note_path=str(note_path),
        source_files=source_file_list_payload(note, paths, session),
        created_at=note.created_at,
        updated_at=note.updated_at,
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
        paths = workspace_paths_for_session(session)
        matches = search_markdown_files(paths.markdown_root, q, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    notes_by_path = notes_by_matched_path(
        session,
        [match.path for match in matches],
        paths,
    )
    matched_notes = {note.id: note for note in notes_by_path.values()}
    starred_ids = starred_note_ids(session, list(matched_notes), user.id)
    results: list[SearchResult] = []
    for match in matches:
        note = notes_by_path.get(str(match.path))
        if note is None:
            continue
        results.append(
            SearchResult(
                note=_note_list_item(
                    note,
                    is_starred=note.id in starred_ids,
                    paths=paths,
                    session=session,
                ),
                line_number=match.line_number,
                column=match.column,
                excerpt=match.excerpt,
            )
        )
    return results
