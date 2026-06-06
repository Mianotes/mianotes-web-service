from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.api.search import _note_list_item
from mianotes_web_service.db.models import Folder, Note
from mianotes_web_service.domain.schemas import ContextResponse, ContextResult
from mianotes_web_service.services.note_path_lookup import notes_by_matched_path
from mianotes_web_service.services.note_responses import starred_note_ids
from mianotes_web_service.services.paths import WorkspacePaths, workspace_paths_for_session
from mianotes_web_service.services.search import search_markdown_files
from mianotes_web_service.services.storage import slugify

router = APIRouter(prefix="/context", tags=["context"])
TITLE_CONTEXT_TEXT_CHARS = 100_000
SEARCH_CONTEXT_TEXT_CHARS = 16_000


def _normalized(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _read_note_text(note: Note, paths: WorkspacePaths, *, max_chars: int) -> str | None:
    try:
        with paths.note_file_path(note).open(encoding="utf-8") as note_file:
            return note_file.read(max_chars)
    except OSError:
        return None


def _matching_folders(session: Session, folder: str) -> list[Folder]:
    folder_slug = slugify(folder, "folder")
    folder_name = _normalized(folder)
    return session.scalars(
        select(Folder).where(
            Folder.archived_at.is_(None),
            (func.lower(Folder.name) == folder_name) | (func.lower(Folder.slug) == folder_slug),
        )
    ).all()


def _title_match_query(folder_ids: list[str], title_query: str, *, exact: bool):
    title_expression = func.lower(Note.title)
    title_filter = (
        title_expression == title_query
        if exact
        else title_expression.contains(title_query, autoescape=True)
    )
    return (
        select(Note)
        .where(Note.folder_id.in_(folder_ids), title_filter)
        .options(
            selectinload(Note.folder),
            selectinload(Note.source_files),
            selectinload(Note.tags),
        )
        .order_by(Note.updated_at.desc())
    )


def _title_matches(
    session: Session,
    *,
    folder_ids: list[str],
    title_query: str,
    limit: int,
    exact: bool,
    seen_note_ids: set[str],
) -> list[Note]:
    if limit <= 0:
        return []
    statement = _title_match_query(folder_ids, title_query, exact=exact)
    if seen_note_ids:
        statement = statement.where(Note.id.not_in(seen_note_ids))
    return list(session.scalars(statement.limit(limit)))


@router.get("", response_model=ContextResponse)
def get_context(
    session: SessionDep,
    user: NotesReadUser,
    folder: Annotated[str, Query(min_length=1, max_length=200)],
    title: Annotated[str, Query(min_length=1, max_length=300)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> ContextResponse:
    folders = _matching_folders(session, folder)
    if not folders:
        return ContextResponse(folder=folder, title=title, limit=limit, total=0, results=[])

    paths = workspace_paths_for_session(session)
    folder_ids = [item.id for item in folders]
    title_query = _normalized(title)
    results: list[ContextResult] = []
    seen_note_ids: set[str] = set()

    def add_title_matches(notes: list[Note]) -> None:
        starred_ids = starred_note_ids(session, [note.id for note in notes], user.id)
        for note in notes:
            if len(results) >= limit or note.id in seen_note_ids:
                continue
            text = _read_note_text(note, paths, max_chars=TITLE_CONTEXT_TEXT_CHARS)
            if text is None:
                continue
            seen_note_ids.add(note.id)
            results.append(
                ContextResult(
                    note=_note_list_item(
                        note,
                        is_starred=note.id in starred_ids,
                        paths=paths,
                        session=session,
                    ),
                    text=text,
                    matched_by="title",
                )
            )

    exact_matches = _title_matches(
        session,
        folder_ids=folder_ids,
        title_query=title_query,
        limit=limit,
        exact=True,
        seen_note_ids=seen_note_ids,
    )
    add_title_matches(exact_matches)
    partial_matches = _title_matches(
        session,
        folder_ids=folder_ids,
        title_query=title_query,
        limit=limit - len(results),
        exact=False,
        seen_note_ids=seen_note_ids,
    )
    add_title_matches(partial_matches)

    if len(results) < limit:
        try:
            matches = search_markdown_files(paths.markdown_root, title, limit=limit * 10)
        except RuntimeError:
            matches = []
        notes_by_path = notes_by_matched_path(
            session,
            [match.path for match in matches],
            paths,
            folder_ids=folder_ids,
        )
        starred_ids = starred_note_ids(
            session,
            list({note.id for note in notes_by_path.values()}),
            user.id,
        )
        for match in matches:
            if len(results) >= limit:
                break
            note = notes_by_path.get(str(match.path))
            if note is None or note.id in seen_note_ids:
                continue
            text = _read_note_text(note, paths, max_chars=SEARCH_CONTEXT_TEXT_CHARS)
            if text is None:
                continue
            seen_note_ids.add(note.id)
            results.append(
                ContextResult(
                    note=_note_list_item(
                        note,
                        is_starred=note.id in starred_ids,
                        paths=paths,
                        session=session,
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
