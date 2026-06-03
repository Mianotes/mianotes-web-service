from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Note
from mianotes_web_service.domain.schemas import NoteListItem, SearchResult
from mianotes_web_service.services.note_path_lookup import notes_by_matched_path
from mianotes_web_service.services.note_responses import starred_note_ids
from mianotes_web_service.services.paths import (
    WorkspacePaths,
    note_file_path,
    source_file_path,
    workspace_paths_for_session,
)
from mianotes_web_service.services.search import search_markdown_files
from mianotes_web_service.services.workspace_context import current_data_dir

router = APIRouter(prefix="/search", tags=["search"])


def _file_url(request: Request, path: str | Path, data_dir: Path | None = None) -> str:
    data_dir = (data_dir or current_data_dir(get_settings().data_dir)).resolve()
    target = Path(path).resolve()
    try:
        public_path = target.relative_to(data_dir)
    except ValueError:
        public_path = Path(path)
    return f"/{public_path.as_posix().lstrip('/')}"


def _source_file_list_payload(
    note: Note,
    request: Request,
    paths: WorkspacePaths | None = None,
) -> list[dict[str, object]]:
    return [
        {
            "id": source_file.id,
            "file_path": str(
                paths.source_file_path(source_file)
                if paths is not None
                else source_file_path(source_file)
            ),
            "original_filename": source_file.original_filename,
            "content_type": source_file.content_type,
            "url": _file_url(
                request,
                paths.source_file_path(source_file)
                if paths is not None
                else source_file_path(source_file),
                paths.data_dir if paths is not None else None,
            ),
        }
        for source_file in note.source_files
    ]


def _note_list_item(
    note: Note,
    request: Request,
    *,
    is_starred: bool,
    paths: WorkspacePaths | None = None,
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
        source_files=_source_file_list_payload(note, request, paths),
        created_at=note.created_at,
        updated_at=note.updated_at,
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
                    request,
                    is_starred=note.id in starred_ids,
                    paths=paths,
                ),
                line_number=match.line_number,
                column=match.column,
                excerpt=match.excerpt,
            )
        )
    return results
