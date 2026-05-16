from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def make_username(email: str) -> str:
    normalized = email.strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:16]


def slugify(value: str, fallback: str = "untitled") -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or fallback


@dataclass(frozen=True)
class NotePaths:
    directory: Path
    note_path: Path
    comments_path: Path
    source_path: Path | None = None


class FilesystemStorage:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def project_dir(self, username: str, project: str) -> Path:
        return self.data_dir / slugify(username, "user") / slugify(project, "project")

    def note_paths(
        self,
        *,
        username: str,
        project: str,
        filename: str,
        source_extension: str | None = None,
        source_suffix: str = "",
    ) -> NotePaths:
        base_dir = self.project_dir(username, project)
        stem = slugify(Path(filename).stem)
        note_path = base_dir / f"{stem}.md"
        comments_path = base_dir / f"{stem}.comments.json"
        source_path = None
        if source_extension:
            extension = (
                source_extension if source_extension.startswith(".") else f".{source_extension}"
            )
            source_path = base_dir / f"{stem}{source_suffix}{extension.lower()}"
        return NotePaths(
            directory=base_dir,
            note_path=note_path,
            comments_path=comments_path,
            source_path=source_path,
        )

    def write_text_note(
        self,
        *,
        username: str,
        project: str,
        title: str,
        text: str,
        filename: str | None = None,
    ) -> NotePaths:
        paths = self.note_paths(
            username=username,
            project=project,
            filename=filename or title,
            source_extension=".source.txt",
        )
        paths.directory.mkdir(parents=True, exist_ok=True)
        paths.note_path.write_text(render_markdown_note(title=title, text=text), encoding="utf-8")
        if paths.source_path is not None:
            paths.source_path.write_text(text, encoding="utf-8")
        return paths

    def write_uploaded_file_note(
        self,
        *,
        username: str,
        project: str,
        title: str,
        filename: str,
        original_filename: str,
        source_stream: BinaryIO,
    ) -> NotePaths:
        extension = Path(original_filename).suffix or ".bin"
        paths = self.note_paths(
            username=username,
            project=project,
            filename=filename,
            source_extension=extension,
            source_suffix=".source",
        )
        paths.directory.mkdir(parents=True, exist_ok=True)
        paths.note_path.write_text(
            render_pending_upload_note(title=title, original_filename=original_filename),
            encoding="utf-8",
        )
        if paths.source_path is not None:
            with paths.source_path.open("wb") as destination:
                shutil.copyfileobj(source_stream, destination)
        return paths

    def write_url_note_placeholder(
        self,
        *,
        username: str,
        project: str,
        title: str,
        filename: str,
        url: str,
    ) -> NotePaths:
        paths = self.note_paths(
            username=username,
            project=project,
            filename=filename,
            source_extension=".source.html",
        )
        paths.directory.mkdir(parents=True, exist_ok=True)
        paths.note_path.write_text(
            render_pending_url_note(title=title, url=url),
            encoding="utf-8",
        )
        return paths


def infer_title(text: str, fallback: str = "Untitled Note") -> str:
    compact = " ".join(text.strip().split())
    if not compact:
        return fallback
    return compact[:80].rstrip(" .,;:-") or fallback


def render_markdown_note(title: str, text: str) -> str:
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"# {title}\n\nCreated: {created_at}\n\n## Note\n\n{text.strip()}\n"


def render_pending_upload_note(title: str, original_filename: str) -> str:
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return (
        f"# {title}\n\n"
        f"Created: {created_at}\n\n"
        "Status: Pending parsing\n\n"
        "## Source\n\n"
        f"{original_filename}\n\n"
        "## Note\n\n"
        "This uploaded file has been stored and is waiting for the parsing pipeline.\n"
    )


def render_pending_url_note(title: str, url: str) -> str:
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return (
        f"# {title}\n\n"
        f"Created: {created_at}\n\n"
        "Status: Pending parsing\n\n"
        "## Source\n\n"
        f"{url}\n\n"
        "## Note\n\n"
        "This link has been queued and is waiting for the parsing pipeline.\n"
    )


def replace_markdown_title(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        lines[0] = f"# {title}"
        return "\n".join(lines) + ("\n" if markdown.endswith("\n") else "")
    return f"# {title}\n\n{markdown}"
