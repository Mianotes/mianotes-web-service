from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Folder, Note
from mianotes_web_service.services.storage import (
    MARKDOWN_DIRNAME,
    slugify,
    summarize_markdown_note,
)

COMPATIBLE_MARKDOWN_IMPORT_MESSAGE = (
    "This folder contains compatible Markdown notes, but no workspace database was found. "
    "Import the notes and create a new Mianotes database for this workspace?"
)
COMPATIBLE_MARKDOWN_FILENAME_PATTERN = re.compile(
    r"^(?P<title_slug>.+)-(?P<note_suffix>[A-Za-z0-9]{8,36})\.md$"
)
TITLE_CASE_ACRONYMS = {"ai", "api", "csv", "html", "llm", "mcp", "pdf", "ui", "url"}


@dataclass(frozen=True)
class CompatibleMarkdownNote:
    folder_path: str
    folder_name: str
    file_path: Path
    filename: str
    title: str
    summary: str
    timestamp: datetime


def find_compatible_markdown_notes(workspace_folder: Path) -> list[CompatibleMarkdownNote]:
    markdown_root = workspace_folder / MARKDOWN_DIRNAME
    if not markdown_root.is_dir():
        return []

    candidates: list[CompatibleMarkdownNote] = []
    for folder_directory in sorted(markdown_root.iterdir()):
        if not folder_directory.is_dir() or folder_directory.name.startswith("."):
            continue
        for file_path in sorted(folder_directory.glob("*.md")):
            match = COMPATIBLE_MARKDOWN_FILENAME_PATTERN.match(file_path.name)
            if match is None:
                continue
            markdown = _read_compatible_markdown(file_path)
            if markdown is None:
                continue
            candidates.append(
                CompatibleMarkdownNote(
                    folder_path=folder_directory.name,
                    folder_name=_display_name_from_slug(folder_directory.name),
                    file_path=file_path,
                    filename=file_path.name,
                    title=_title_from_markdown(markdown, match.group("title_slug")),
                    summary=summarize_markdown_note(markdown),
                    timestamp=datetime.fromtimestamp(file_path.stat().st_mtime, UTC),
                )
            )
    return candidates


def _read_compatible_markdown(file_path: Path) -> str | None:
    try:
        return file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def has_compatible_markdown_notes(workspace_folder: Path) -> bool:
    return bool(find_compatible_markdown_notes(workspace_folder))


def import_compatible_markdown_notes(
    session: Session,
    *,
    workspace_folder: Path,
    user_id: str,
) -> int:
    candidates = find_compatible_markdown_notes(workspace_folder)
    folders_by_path: dict[str, Folder] = {
        folder.path: folder for folder in session.scalars(select(Folder)).all()
    }
    imported_count = 0

    for candidate in candidates:
        folder = folders_by_path.get(candidate.folder_path)
        if folder is None:
            folder = Folder(
                user_id=user_id,
                name=candidate.folder_name,
                slug=slugify(candidate.folder_path, "folder"),
                path=candidate.folder_path,
                created_at=candidate.timestamp,
                updated_at=candidate.timestamp,
            )
            session.add(folder)
            session.flush()
            folders_by_path[candidate.folder_path] = folder

        existing_note = session.scalars(
            select(Note).where(
                Note.folder_id == folder.id,
                Note.filename == candidate.filename,
            )
        ).one_or_none()
        if existing_note is not None:
            continue

        session.add(
            Note(
                user_id=user_id,
                folder_id=folder.id,
                title=candidate.title,
                filename=candidate.filename,
                note_path=str(candidate.file_path),
                summary=candidate.summary,
                created_at=candidate.timestamp,
                updated_at=candidate.timestamp,
            )
        )
        imported_count += 1

    return imported_count


def _title_from_markdown(markdown: str, fallback_slug: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or _display_name_from_slug(fallback_slug)
    return _display_name_from_slug(fallback_slug)


def _display_name_from_slug(value: str) -> str:
    words = [word for word in value.replace("_", "-").split("-") if word]
    if not words:
        return "Untitled"
    return " ".join(
        word.upper() if word.lower() in TITLE_CASE_ACRONYMS else word.capitalize()
        for word in words
    )
