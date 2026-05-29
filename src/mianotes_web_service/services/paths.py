from __future__ import annotations

from pathlib import Path

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Folder, Note, SourceFile
from mianotes_web_service.services.storage import MARKDOWN_DIRNAME
from mianotes_web_service.services.workspace_context import current_data_dir


def markdown_root(data_dir: Path | None = None) -> Path:
    root = data_dir if data_dir is not None else current_data_dir(get_settings().data_dir)
    return root / MARKDOWN_DIRNAME


def folder_directory(folder: Folder, data_dir: Path | None = None) -> Path:
    return markdown_root(data_dir) / folder.path


def note_file_path(note: Note, data_dir: Path | None = None) -> Path:
    if note.filename and note.folder is not None:
        return folder_directory(note.folder, data_dir) / note.filename
    return Path(note.note_path)


def source_file_path(source_file: SourceFile, data_dir: Path | None = None) -> Path:
    if (
        source_file.filename
        and source_file.note is not None
        and source_file.note.folder is not None
    ):
        return folder_directory(source_file.note.folder, data_dir) / source_file.filename
    return Path(source_file.file_path)


def note_image_directory(note: Note, data_dir: Path | None = None) -> Path:
    if note.folder is not None:
        return folder_directory(note.folder, data_dir) / "images" / note.id[:8]
    return Path(note.note_path).parent / "images" / note.id[:8]


def relative_to_folder(folder: Folder, path: Path, data_dir: Path | None = None) -> str:
    return str(path.relative_to(folder_directory(folder, data_dir)))
