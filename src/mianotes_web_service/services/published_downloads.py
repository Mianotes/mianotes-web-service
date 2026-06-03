from __future__ import annotations

import os
import re
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from mianotes_web_service.db.models import PublishedSite

ZIP_STREAM_CHUNK_SIZE = 1024 * 1024


class PublishedSiteFilesNotFoundError(Exception):
    pass


class PublishedSiteDownloadLimitError(Exception):
    pass


@dataclass(frozen=True)
class PublishedSiteArchive:
    path: Path
    filename: str


@dataclass(frozen=True)
class ArchiveEntry:
    source: Path
    name: str
    size: int


def archive_name(site: PublishedSite) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", site.version.strip()).strip(".-_")
    return value or "mianotes"


def build_published_site_archive(
    site: PublishedSite,
    *,
    data_dir: Path,
    max_bytes: int,
    max_files: int,
) -> PublishedSiteArchive:
    html_root = (data_dir / "html").resolve()
    site_dir = (data_dir / site.html_path).resolve()
    if html_root not in site_dir.parents or not site_dir.is_dir():
        raise PublishedSiteFilesNotFoundError()

    archive_root = f"{archive_name(site)}-static-site"
    entries = _archive_entries(
        data_dir=data_dir,
        html_root=html_root,
        site_dir=site_dir,
        archive_root=archive_root,
    )
    _enforce_archive_limits(entries, max_bytes=max_bytes, max_files=max_files)

    archive_path = _write_zip_file(entries)
    if archive_path.stat().st_size > max_bytes:
        archive_path.unlink(missing_ok=True)
        raise PublishedSiteDownloadLimitError()
    return PublishedSiteArchive(path=archive_path, filename=f"{archive_root}.zip")


def stream_file_and_remove(path: Path, chunk_size: int = ZIP_STREAM_CHUNK_SIZE) -> Iterator[bytes]:
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                yield chunk
    finally:
        path.unlink(missing_ok=True)


def _archive_entries(
    *,
    data_dir: Path,
    html_root: Path,
    site_dir: Path,
    archive_root: str,
) -> list[ArchiveEntry]:
    entries: list[ArchiveEntry] = []
    toc_path = data_dir / "TOC.md"
    if toc_path.is_file() and not toc_path.is_symlink():
        entries.append(_entry(toc_path, f"{archive_root}/TOC.md"))

    for file_path in (
        html_root / "index.html",
        html_root / "navigation.js",
        html_root / "latest" / "index.html",
    ):
        safe_path = _safe_html_file(file_path, html_root)
        if safe_path is not None:
            entries.append(
                _entry(
                    safe_path,
                    f"{archive_root}/{safe_path.relative_to(html_root).as_posix()}",
                )
            )

    for file_path in sorted(site_dir.rglob("*")):
        safe_path = _safe_html_file(file_path, html_root)
        if safe_path is None:
            continue
        entries.append(
            _entry(
                safe_path,
                f"{archive_root}/{safe_path.relative_to(html_root).as_posix()}",
            )
        )

    return entries


def _entry(source: Path, name: str) -> ArchiveEntry:
    return ArchiveEntry(source=source, name=name, size=source.stat().st_size)


def _safe_html_file(path: Path, html_root: Path) -> Path | None:
    if path.is_symlink() or not path.is_file():
        return None
    resolved = path.resolve()
    if html_root not in resolved.parents:
        return None
    return resolved


def _enforce_archive_limits(
    entries: list[ArchiveEntry],
    *,
    max_bytes: int,
    max_files: int,
) -> None:
    if len(entries) > max_files:
        raise PublishedSiteDownloadLimitError()
    if sum(entry.size for entry in entries) > max_bytes:
        raise PublishedSiteDownloadLimitError()


def _write_zip_file(entries: list[ArchiveEntry]) -> Path:
    handle = tempfile.NamedTemporaryFile(
        prefix="mianotes-published-site-",
        suffix=".zip",
        delete=False,
    )
    archive_path = Path(handle.name)
    handle.close()
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for entry in entries:
                zip_file.write(entry.source, entry.name)
    except Exception:
        os.unlink(archive_path)
        raise
    return archive_path
