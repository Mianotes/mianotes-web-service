from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Folder, Note, SourceFile
from mianotes_web_service.services.storage import MARKDOWN_DIRNAME
from mianotes_web_service.services.workspace_context import current_data_dir, session_data_dir


@dataclass(frozen=True)
class WorkspacePaths:
    """Resolve filesystem paths for one workspace.

    Request handlers should create this from the request SQLAlchemy session so the
    database and filesystem always point at the same workspace. The ambient
    ContextVar fallback is reserved for background jobs and non-request flows.
    """

    data_dir: Path

    @property
    def markdown_root(self) -> Path:
        return self.data_dir / MARKDOWN_DIRNAME

    def folder_directory(self, folder: Folder) -> Path:
        return self.markdown_root / folder.path

    def note_file_path(self, note: Note) -> Path:
        if note.filename and note.folder is not None:
            return self.folder_directory(note.folder) / note.filename
        return Path(note.note_path)

    def source_file_path(self, source_file: SourceFile) -> Path:
        if (
            source_file.filename
            and source_file.note is not None
            and source_file.note.folder is not None
        ):
            return self.folder_directory(source_file.note.folder) / source_file.filename
        return Path(source_file.file_path)

    def note_image_directory(self, note: Note) -> Path:
        if note.folder is not None:
            return self.folder_directory(note.folder) / "images" / note.id[:8]
        return Path(note.note_path).parent / "images" / note.id[:8]

    def relative_to_folder(self, folder: Folder, path: Path) -> str:
        return str(path.relative_to(self.folder_directory(folder)))


def current_workspace_paths() -> WorkspacePaths:
    return WorkspacePaths(current_data_dir(get_settings().data_dir))


def workspace_paths_for_session(session: Any) -> WorkspacePaths:
    return WorkspacePaths(session_data_dir(session, get_settings().data_dir))


def workspace_paths_for_data_dir(data_dir: Path | None = None) -> WorkspacePaths:
    return WorkspacePaths(data_dir) if data_dir is not None else current_workspace_paths()


def markdown_root(data_dir: Path | None = None) -> Path:
    return workspace_paths_for_data_dir(data_dir).markdown_root


def folder_directory(folder: Folder, data_dir: Path | None = None) -> Path:
    return workspace_paths_for_data_dir(data_dir).folder_directory(folder)


def note_file_path(note: Note, data_dir: Path | None = None) -> Path:
    return workspace_paths_for_data_dir(data_dir).note_file_path(note)


def source_file_path(source_file: SourceFile, data_dir: Path | None = None) -> Path:
    return workspace_paths_for_data_dir(data_dir).source_file_path(source_file)


def note_image_directory(note: Note, data_dir: Path | None = None) -> Path:
    return workspace_paths_for_data_dir(data_dir).note_image_directory(note)


def relative_to_folder(folder: Folder, path: Path, data_dir: Path | None = None) -> str:
    return workspace_paths_for_data_dir(data_dir).relative_to_folder(folder, path)
