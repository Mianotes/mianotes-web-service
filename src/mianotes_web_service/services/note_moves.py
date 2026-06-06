from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Folder, Note, SourceFile
from mianotes_web_service.services.filesystem_uow import FilesystemUnitOfWork
from mianotes_web_service.services.paths import (
    folder_directory,
    note_file_path,
    note_image_directory,
    source_file_path,
)
from mianotes_web_service.services.storage import FilesystemStorage
from mianotes_web_service.services.workspace_context import current_data_dir


def validate_stored_moves(moves: list[tuple[Path, Path]]) -> None:
    for current_path, target_path in moves:
        if current_path.resolve() == target_path.resolve():
            continue
        if not current_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note file not found",
            )
        if target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A file already exists in the target folder",
            )


def move_note_to_folder(
    note: Note,
    target_folder: Folder,
    *,
    data_dir: Path | None = None,
    filesystem: FilesystemUnitOfWork,
) -> None:
    if note.folder_id == target_folder.id:
        return

    current_folder = note.folder
    workspace_data_dir = data_dir or current_data_dir(get_settings().data_dir)
    current_folder_dir = (
        folder_directory(current_folder, workspace_data_dir) if current_folder else None
    )
    target_folder_dir = folder_directory(target_folder, workspace_data_dir)
    FilesystemStorage(workspace_data_dir).prepare_folder_directory(target_folder_dir)

    current_note_path = note_file_path(note, workspace_data_dir)
    note_filename = note.filename or current_note_path.name
    target_note_path = target_folder_dir / note_filename
    source_moves: list[tuple[SourceFile, Path, Path, str]] = []

    for source_file in note.source_files:
        current_source_path = source_file_path(source_file, workspace_data_dir)
        source_filename = source_file.filename
        if not source_filename and current_folder_dir is not None:
            try:
                source_filename = current_source_path.relative_to(current_folder_dir).as_posix()
            except ValueError:
                source_filename = None
        if not source_filename:
            continue
        source_moves.append(
            (
                source_file,
                current_source_path,
                target_folder_dir / source_filename,
                source_filename,
            )
        )

    current_image_dir = note_image_directory(note, workspace_data_dir)
    target_image_dir = target_folder_dir / "images" / note.id[:8]

    path_moves = [
        (current_note_path, target_note_path),
        *[
            (current_source_path, target_source_path)
            for _, current_source_path, target_source_path, _ in source_moves
        ],
    ]
    if current_image_dir.exists():
        path_moves.append((current_image_dir, target_image_dir))
    validate_stored_moves(path_moves)

    filesystem.move_path(current_note_path, target_note_path)
    for source_file, current_source_path, target_source_path, source_filename in source_moves:
        filesystem.move_path(current_source_path, target_source_path)
        source_file.filename = source_filename
        source_file.file_path = str(target_source_path)
    if current_image_dir.exists():
        filesystem.move_path(current_image_dir, target_image_dir)

    note.folder_id = target_folder.id
    note.folder = target_folder
    note.filename = note_filename
    note.note_path = str(target_note_path)
