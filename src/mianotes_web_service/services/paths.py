from __future__ import annotations

from pathlib import Path

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Note, Project, SourceFile


def project_directory(project: Project) -> Path:
    return get_settings().data_dir / project.path


def note_file_path(note: Note) -> Path:
    if note.filename and note.project is not None:
        return project_directory(note.project) / note.filename
    return Path(note.note_path)


def source_file_path(source_file: SourceFile) -> Path:
    if (
        source_file.filename
        and "/" in source_file.filename
        and source_file.note is not None
        and source_file.note.project is not None
    ):
        return project_directory(source_file.note.project) / source_file.filename
    return Path(source_file.file_path)


def relative_to_project(project: Project, path: Path) -> str:
    return str(path.relative_to(project_directory(project)))
