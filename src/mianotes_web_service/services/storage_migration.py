from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.db.models import Note, SourceFile, User
from mianotes_web_service.services.storage import make_username, note_stem


@dataclass(frozen=True)
class StoragePathMigrationResult:
    users_updated: int = 0
    notes_updated: int = 0
    source_files_updated: int = 0
    files_moved: int = 0


def migrate_readable_storage_paths(
    session: Session,
    *,
    data_dir: Path,
) -> StoragePathMigrationResult:
    users_updated = _migrate_usernames(session)
    session.flush()

    notes_updated = 0
    source_files_updated = 0
    files_moved = 0

    statement = select(Note).options(
        joinedload(Note.user),
        joinedload(Note.project),
        joinedload(Note.source_files),
    )
    notes = session.scalars(statement).unique().all()
    for note in notes:
        base_dir = data_dir / note.user.username / note.project.slug
        stem = note_stem(note.title, note.id)

        next_note_path = base_dir / f"{stem}.md"
        moved = _move_if_needed(Path(note.note_path), next_note_path)
        if note.note_path != str(next_note_path):
            note.note_path = str(next_note_path)
            notes_updated += 1
        files_moved += int(moved)

        for source_file in note.source_files:
            next_source_path = base_dir / f"{stem}.source{_source_extension(source_file)}"
            moved = _move_if_needed(Path(source_file.file_path), next_source_path)
            if source_file.file_path != str(next_source_path):
                source_file.file_path = str(next_source_path)
                source_files_updated += 1
            files_moved += int(moved)

    session.commit()
    return StoragePathMigrationResult(
        users_updated=users_updated,
        notes_updated=notes_updated,
        source_files_updated=source_files_updated,
        files_moved=files_moved,
    )


def _migrate_usernames(session: Session) -> int:
    users = session.scalars(select(User)).all()
    updated = 0
    for user in users:
        next_username = make_username(user.email, user.name)
        if user.username == next_username:
            continue
        user.username = next_username
        updated += 1
    return updated


def _source_extension(source_file: SourceFile) -> str:
    suffix = Path(source_file.file_path).suffix
    if suffix:
        return suffix.lower()
    suffix = Path(source_file.original_filename).suffix
    return suffix.lower() if suffix else ".bin"


def _move_if_needed(current_path: Path, next_path: Path) -> bool:
    if current_path == next_path:
        return False
    if not current_path.exists():
        return False
    next_path.parent.mkdir(parents=True, exist_ok=True)
    if next_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {next_path}")
    shutil.move(str(current_path), str(next_path))
    return True
