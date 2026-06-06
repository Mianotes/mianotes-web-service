from __future__ import annotations

from pathlib import Path

from mianotes_web_service.db.models import Note
from mianotes_web_service.services.filesystem_uow import FilesystemUnitOfWork
from mianotes_web_service.services.paths import WorkspacePaths


def stage_note_files_for_delete(
    note: Note,
    paths: WorkspacePaths,
    filesystem: FilesystemUnitOfWork,
) -> None:
    markdown_root = paths.markdown_root.resolve()
    for target_path in _managed_note_paths(note, paths):
        if _is_inside(target_path, markdown_root):
            filesystem.delete_path(target_path)


def _managed_note_paths(note: Note, paths: WorkspacePaths) -> list[Path]:
    source_file_paths = [paths.source_file_path(source_file) for source_file in note.source_files]
    return [
        paths.note_file_path(note),
        *source_file_paths,
        paths.note_image_directory(note),
    ]


def _is_inside(target_path: Path, root: Path) -> bool:
    try:
        target_path.resolve().relative_to(root)
    except ValueError:
        return False
    return True
