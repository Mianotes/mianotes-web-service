from __future__ import annotations

from fastapi import HTTPException, status

from mianotes_web_service.db.models import Note
from mianotes_web_service.services.paths import WorkspacePaths


def delete_note_markdown_file(note: Note, paths: WorkspacePaths) -> None:
    note_path = paths.note_file_path(note).resolve()
    markdown_root = paths.markdown_root.resolve()

    try:
        note_path.relative_to(markdown_root)
    except ValueError:
        return

    if not note_path.exists():
        return

    if not note_path.is_file():
        return

    try:
        note_path.unlink()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete note file",
        ) from exc
