from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mianotes_web_service.db.models import Note
from mianotes_web_service.services.paths import WorkspacePaths


def candidate_note_path_values(match_path: Path, paths: WorkspacePaths) -> set[str]:
    resolved_path = match_path.resolve()
    values = {str(match_path), str(resolved_path)}
    try:
        values.add(str(resolved_path.relative_to(paths.data_dir.resolve())))
    except ValueError:
        pass
    try:
        values.add(str(resolved_path.relative_to(paths.markdown_root.resolve())))
    except ValueError:
        pass
    return values


def resolved_note_paths(note: Note, paths: WorkspacePaths) -> set[str]:
    values = {note.note_path}
    try:
        path = paths.note_file_path(note)
        values.add(str(path))
        values.add(str(path.resolve()))
    except OSError:
        pass
    return values


def notes_by_matched_path(
    session: Session,
    matched_paths: Iterable[Path],
    paths: WorkspacePaths,
    *,
    folder_ids: Iterable[str] | None = None,
) -> dict[str, Note]:
    note_path_values = {
        value
        for matched_path in matched_paths
        for value in candidate_note_path_values(matched_path, paths)
    }
    if not note_path_values:
        return {}

    statement = (
        select(Note)
        .options(
            selectinload(Note.folder),
            selectinload(Note.source_files),
            selectinload(Note.tags),
        )
        .where(Note.note_path.in_(note_path_values))
    )
    if folder_ids is not None:
        folder_id_values = list(folder_ids)
        if not folder_id_values:
            return {}
        statement = statement.where(Note.folder_id.in_(folder_id_values))

    by_path: dict[str, Note] = {}
    for note in session.scalars(statement):
        for note_path in resolved_note_paths(note, paths):
            by_path[note_path] = note
    return by_path
