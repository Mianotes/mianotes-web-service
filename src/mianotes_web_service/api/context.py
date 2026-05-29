from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.api.search import _is_starred_by_user, _note_list_item
from mianotes_web_service.db.models import Folder, Note
from mianotes_web_service.domain.schemas import ContextResponse, ContextResult
from mianotes_web_service.services.paths import WorkspacePaths, workspace_paths_for_session
from mianotes_web_service.services.search import search_markdown_files
from mianotes_web_service.services.storage import slugify

router = APIRouter(prefix="/context", tags=["context"])


def _normalized(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _read_note_text(note: Note, paths: WorkspacePaths) -> str | None:
    try:
        return paths.note_file_path(note).read_text(encoding="utf-8")
    except OSError:
        return None


@router.get("", response_model=ContextResponse)
def get_context(
    session: SessionDep,
    request: Request,
    user: NotesReadUser,
    folder: Annotated[str, Query(min_length=1, max_length=200)],
    title: Annotated[str, Query(min_length=1, max_length=300)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> ContextResponse:
    folder_slug = slugify(folder, "folder")
    folder_name = _normalized(folder)
    folders = session.scalars(
        select(Folder).where(
            Folder.archived_at.is_(None),
            (func.lower(Folder.name) == folder_name) | (func.lower(Folder.slug) == folder_slug),
        )
    ).all()
    if not folders:
        return ContextResponse(folder=folder, title=title, limit=limit, total=0, results=[])

    paths = workspace_paths_for_session(session)
    folder_ids = [item.id for item in folders]
    notes = (
        session.scalars(
            select(Note)
            .where(Note.folder_id.in_(folder_ids))
            .options(
                joinedload(Note.folder),
                joinedload(Note.source_files),
                joinedload(Note.comments),
                joinedload(Note.tags),
            )
            .order_by(Note.updated_at.desc())
        )
        .unique()
        .all()
    )

    title_query = _normalized(title)
    results: list[ContextResult] = []
    seen_note_ids: set[str] = set()

    def add_title_matches(predicate) -> None:
        for note in notes:
            if len(results) >= limit or note.id in seen_note_ids or not predicate(note):
                continue
            text = _read_note_text(note, paths)
            if text is None:
                continue
            seen_note_ids.add(note.id)
            results.append(
                ContextResult(
                    note=_note_list_item(
                        note,
                        request,
                        is_starred=_is_starred_by_user(session, note.id, user.id),
                        paths=paths,
                    ),
                    text=text,
                    matched_by="title",
                )
            )

    add_title_matches(lambda note: _normalized(note.title) == title_query)
    add_title_matches(lambda note: title_query in _normalized(note.title))

    if len(results) < limit:
        notes_by_path = {str(paths.note_file_path(note).resolve()): note for note in notes}
        try:
            matches = search_markdown_files(paths.markdown_root, title, limit=limit * 10)
        except RuntimeError:
            matches = []
        for match in matches:
            if len(results) >= limit:
                break
            note = notes_by_path.get(str(match.path))
            if note is None or note.id in seen_note_ids:
                continue
            text = _read_note_text(note, paths)
            if text is None:
                continue
            seen_note_ids.add(note.id)
            results.append(
                ContextResult(
                    note=_note_list_item(
                        note,
                        request,
                        is_starred=_is_starred_by_user(session, note.id, user.id),
                        paths=paths,
                    ),
                    text=text,
                    matched_by="search",
                    line_number=match.line_number,
                    excerpt=match.excerpt,
                )
            )

    return ContextResponse(
        folder=folder,
        title=title,
        limit=limit,
        total=len(results),
        results=results,
    )
