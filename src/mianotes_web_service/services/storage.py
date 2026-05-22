from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
MARKDOWN_DIRNAME = "markdown"


def make_username(email: str, name: str | None = None) -> str:
    normalized = email.strip().lower().encode("utf-8")
    suffix = hashlib.sha256(normalized).hexdigest()[:8]
    if name is None:
        return hashlib.sha256(normalized).hexdigest()[:16]
    return f"{slugify(name, 'user')}-{suffix}"


def slugify(value: str, fallback: str = "untitled") -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or fallback


def short_id(value: str, length: int = 8) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]", "", value).lower()
    return compact[:length] or "00000000"


def note_stem(title: str, note_id: str) -> str:
    return f"{slugify(title)}-{short_id(note_id)}"


@dataclass(frozen=True)
class NotePaths:
    directory: Path
    note_path: Path
    source_path: Path | None = None


class FilesystemStorage:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def folder_dir(self, username: str, folder: str) -> Path:
        # Keep username in the signature while storage paths move to folder-first.
        _ = username
        return self.data_dir / MARKDOWN_DIRNAME / slugify(folder, "folder")

    def prepare_folder_directory(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        gitignore_path = directory / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text("/sources/\n", encoding="utf-8")

    def note_paths(
        self,
        *,
        username: str,
        folder: str,
        filename: str,
        title: str | None = None,
        source_extension: str | None = None,
    ) -> NotePaths:
        base_dir = self.folder_dir(username, folder)
        stem = note_stem(title, filename) if title is not None else slugify(Path(filename).stem)
        note_path = base_dir / f"{stem}.md"
        source_path = None
        if source_extension:
            extension = (
                source_extension if source_extension.startswith(".") else f".{source_extension}"
            )
            source_path = base_dir / "sources" / short_id(filename) / f"original{extension.lower()}"
        return NotePaths(
            directory=base_dir,
            note_path=note_path,
            source_path=source_path,
        )

    def write_text_note(
        self,
        *,
        username: str,
        folder: str,
        title: str,
        text: str,
        filename: str | None = None,
    ) -> NotePaths:
        paths = self.note_paths(
            username=username,
            folder=folder,
            filename=filename or title,
            title=title if filename is not None else None,
            source_extension=".txt" if text.strip() else None,
        )
        self.prepare_folder_directory(paths.directory)
        paths.note_path.write_text(render_markdown_note(title=title, text=text), encoding="utf-8")
        if paths.source_path is not None:
            paths.source_path.parent.mkdir(parents=True, exist_ok=True)
            paths.source_path.write_text(text, encoding="utf-8")
        return paths

    def write_uploaded_file_note(
        self,
        *,
        username: str,
        folder: str,
        title: str,
        filename: str,
        original_filename: str,
        source_stream: BinaryIO,
    ) -> NotePaths:
        extension = Path(original_filename).suffix or ".bin"
        paths = self.note_paths(
            username=username,
            folder=folder,
            filename=filename,
            title=title,
            source_extension=extension,
        )
        self.prepare_folder_directory(paths.directory)
        paths.note_path.write_text(
            render_pending_upload_note(title=title, original_filename=original_filename),
            encoding="utf-8",
        )
        if paths.source_path is not None:
            paths.source_path.parent.mkdir(parents=True, exist_ok=True)
            with paths.source_path.open("wb") as destination:
                shutil.copyfileobj(source_stream, destination)
        return paths

    def write_url_note_placeholder(
        self,
        *,
        username: str,
        folder: str,
        title: str,
        filename: str,
        url: str,
    ) -> NotePaths:
        paths = self.note_paths(
            username=username,
            folder=folder,
            filename=filename,
            title=title,
            source_extension=".html",
        )
        self.prepare_folder_directory(paths.directory)
        if paths.source_path is not None:
            paths.source_path.parent.mkdir(parents=True, exist_ok=True)
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


def summarize_text(text: str, max_words: int = 55) -> str:
    compact = " ".join(text.strip().split())
    compact = re.sub(r"[#>*_`~\[\]()-]+", " ", compact)
    words = compact.split()
    if len(words) <= max_words:
        return " ".join(words)
    return f"{' '.join(words[:max_words]).rstrip(' .,;:-')}..."


def markdown_note_body(markdown: str) -> str:
    lines = markdown.splitlines()
    note_heading_index = next(
        (index for index, line in enumerate(lines) if line.strip().lower() == "## note"),
        None,
    )
    if note_heading_index is not None:
        return "\n".join(lines[note_heading_index + 1 :]).strip()

    body_lines = lines[1:] if lines and lines[0].startswith("# ") else lines
    return "\n".join(
        line
        for line in body_lines
        if not line.strip().startswith(("Created:", "Status:"))
    ).strip()


def summarize_markdown_note(markdown: str, max_words: int = 55) -> str:
    return summarize_text(markdown_note_body(markdown), max_words=max_words)


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
        "Mia is indexing your link. The Markdown note will appear here when the "
        "page has been converted.\n\n"
        f"{url}\n"
    )


def replace_markdown_title(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        lines[0] = f"# {title}"
        return "\n".join(lines) + ("\n" if markdown.endswith("\n") else "")
    return f"# {title}\n\n{markdown}"
