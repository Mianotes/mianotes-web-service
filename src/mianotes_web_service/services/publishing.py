from __future__ import annotations

import html
import json
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Folder, Note, PublishedSite, Tag, User
from mianotes_web_service.domain.schemas import PublishRequest
from mianotes_web_service.services.paths import note_file_path
from mianotes_web_service.services.storage import markdown_note_body, short_id, slugify

PUBLISHABLE_NOTE_STATUSES = ("ready", "published")

THEMES_DIR = Path(__file__).resolve().parents[1] / "publishing" / "themes"
GENERATOR_META_TAG = '<meta name="generator" content="Mianotes - https://github.com/Mianotes">'
DEFAULT_SITE_CONFIGURATION: dict[str, object] = {
    "brand": "mianotes",
    "version": "0.1.0",
    "headerLinks": [
        {"title": "GitHub", "url": "https://github.com/Mianotes"},
        {"title": "Contact", "url": "mailto:mianotes@proton.me"},
    ],
    "showPreviousVersions": True,
    "footerHtml": "Copyright © Your Name Here.",
}


@dataclass(frozen=True)
class PublishTheme:
    id: str
    name: str
    description: str
    version: str
    directory: Path


@dataclass(frozen=True)
class PublishDraft:
    theme: str
    folder_id: str | None
    tag_id: str | None
    site_configuration: dict[str, object]
    navigation: list[dict[str, object]]
    updated_notes: list[dict[str, object]]
    generated_at: datetime


def list_publish_themes() -> list[PublishTheme]:
    themes: list[PublishTheme] = []
    if not THEMES_DIR.exists():
        return themes
    for directory in sorted(path for path in THEMES_DIR.iterdir() if path.is_dir()):
        metadata_path = directory / "theme.json"
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        themes.append(
            PublishTheme(
                id=str(metadata["id"]),
                name=str(metadata["name"]),
                description=str(metadata["description"]),
                version=str(metadata["version"]),
                directory=directory,
            )
        )
    theme_order = {"mialight": 0, "miadark": 1}
    return sorted(themes, key=lambda theme: (theme_order.get(theme.id, 99), theme.name.lower()))


def read_publish_theme(theme_id: str) -> PublishTheme:
    theme = next((theme for theme in list_publish_themes() if theme.id == theme_id), None)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found")
    return theme


def build_publish_draft(
    session: Session,
    *,
    theme_id: str = "mialight",
    folder_id: str | None = None,
    tag_id: str | None = None,
) -> PublishDraft:
    theme = read_publish_theme(theme_id)
    folder = _read_folder(session, folder_id) if folder_id else None
    tag = _read_tag(session, tag_id) if tag_id else None
    notes = _read_publishable_notes(session, folder_id=folder_id, tag_id=tag_id)
    latest_publish = _read_latest_publish(session, folder_id=folder_id, tag_id=tag_id)
    has_previous_publish = latest_publish is not None
    include_folder = folder_id is None
    site_configuration = (
        _load_json_object(latest_publish.site_configuration, DEFAULT_SITE_CONFIGURATION)
        if latest_publish
        else _default_site_configuration(theme)
    )
    navigation = _navigation_for_notes(notes, include_folder=include_folder)
    previous_navigation_paths = (
        _navigation_paths(_load_json_list(latest_publish.navigation, []))
        if latest_publish
        else set()
    )
    updated_notes = [] if not has_previous_publish else _updated_notes(
        notes,
        include_folder=include_folder,
        previous_navigation_paths=previous_navigation_paths,
    )
    return PublishDraft(
        theme=theme.id,
        folder_id=folder.id if folder else None,
        tag_id=tag.id if tag else None,
        site_configuration=site_configuration,
        navigation=navigation,
        updated_notes=updated_notes,
        generated_at=datetime.now(UTC),
    )


def publish_site(session: Session, user: User, payload: PublishRequest) -> PublishedSite:
    theme = read_publish_theme(payload.theme)
    folder = _read_folder(session, payload.folder_id) if payload.folder_id else None
    tag = _read_tag(session, payload.tag_id) if payload.tag_id else None
    notes = _read_publishable_notes(session, folder_id=payload.folder_id, tag_id=payload.tag_id)
    version = str(payload.site_configuration.get("version") or theme.version)
    version_slug = _version_slug(version)
    data_dir = get_settings().data_dir
    html_root = data_dir / "html"
    version_dir = html_root / version_slug
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True, exist_ok=True)

    note_pages, search_index = _write_note_pages(
        notes,
        version_dir=version_dir,
        config=payload.site_configuration,
        include_folder=payload.folder_id is None,
    )
    _write_theme_assets(
        theme,
        version_dir=version_dir,
        config=payload.site_configuration,
        navigation=payload.navigation,
        search_index=search_index,
    )
    _write_version_index(
        version_dir=version_dir,
        config=payload.site_configuration,
        note_pages=note_pages,
    )
    _write_root_index(html_root=html_root, version_slug=version_slug)

    now = datetime.now(UTC)
    note_ids = [note.id for note in notes]
    if note_ids:
        session.execute(
            update(Note)
            .where(Note.id.in_(note_ids))
            .values(
                is_published=True,
                published_at=now,
                updated_at=Note.updated_at,
            )
        )
    published_site = PublishedSite(
        user_id=user.id,
        folder_id=folder.id if folder else None,
        tag_id=tag.id if tag else None,
        theme=theme.id,
        version=version,
        html_path=f"html/{version_slug}",
        markdown_path="",
        url_path=f"html/{version_slug}/index.html",
        site_configuration=json.dumps(payload.site_configuration),
        navigation=json.dumps(payload.navigation),
        note_count=len(notes),
    )
    session.add(published_site)
    session.commit()
    session.refresh(published_site)
    _write_navigation_js(session=session, html_root=html_root, current_site=published_site)
    return published_site


def _read_folder(session: Session, folder_id: str | None) -> Folder:
    folder = session.get(Folder, folder_id)
    if folder is None or folder.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return folder


def _read_tag(session: Session, tag_id: str | None) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


def _read_publishable_notes(
    session: Session,
    *,
    folder_id: str | None,
    tag_id: str | None,
) -> list[Note]:
    statement = (
        select(Note)
        .join(Note.folder)
        .where(Note.status.in_(PUBLISHABLE_NOTE_STATUSES), Folder.archived_at.is_(None))
        .options(joinedload(Note.folder), joinedload(Note.user), joinedload(Note.tags))
        .order_by(Folder.name.asc(), Note.title.asc())
    )
    if folder_id:
        statement = statement.where(Note.folder_id == folder_id)
    if tag_id:
        statement = statement.where(Note.tags.any(Tag.id == tag_id))
    return list(session.scalars(statement).unique())


def _read_latest_publish(
    session: Session,
    *,
    folder_id: str | None,
    tag_id: str | None,
) -> PublishedSite | None:
    statement = select(PublishedSite)
    if folder_id:
        statement = statement.where(PublishedSite.folder_id == folder_id)
    else:
        statement = statement.where(PublishedSite.folder_id.is_(None))
    if tag_id:
        statement = statement.where(PublishedSite.tag_id == tag_id)
    else:
        statement = statement.where(PublishedSite.tag_id.is_(None))
    return session.scalars(statement.order_by(PublishedSite.created_at.desc())).first()


def _site_slug(session: Session, folder_id: str | None) -> str:
    if folder_id is None:
        return "all-folders"
    return _read_folder(session, folder_id).slug


def _navigation_for_notes(notes: list[Note], *, include_folder: bool) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for note in notes:
        folder = note.folder
        groups.setdefault(folder.name, []).append(
            {
                "title": note.title,
                "path": _published_note_path(note, include_folder=include_folder),
            }
        )
    return [{"title": title, "items": items} for title, items in groups.items()]


def _updated_notes(
    notes: list[Note],
    *,
    include_folder: bool,
    previous_navigation_paths: set[str],
) -> list[dict[str, object]]:
    updated_notes: list[dict[str, object]] = []
    for note in notes:
        path = _published_note_path(note, include_folder=include_folder)
        if path in previous_navigation_paths:
            continue
        updated_notes.append(
            {
                "title": note.title,
                "path": path,
            }
        )
    return updated_notes


def _navigation_paths(navigation: list[dict[str, object]]) -> set[str]:
    paths: set[str] = set()

    def collect(items: Iterable[object]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if isinstance(path, str) and path:
                paths.add(path)
            children = item.get("items")
            if isinstance(children, list):
                collect(children)

    collect(navigation)
    return paths


def _published_note_path(note: Note, *, include_folder: bool) -> str:
    filename = f"{slugify(note.title)}-{short_id(note.id)}.html"
    if include_folder:
        return f"{note.folder.slug}/{filename}"
    return filename


def _write_theme_assets(
    theme: PublishTheme,
    *,
    version_dir: Path,
    config: dict[str, object],
    navigation: list[dict[str, object]],
    search_index: list[dict[str, object]],
) -> None:
    shutil.copy2(theme.directory / "styles.css", version_dir / "styles.css")
    site_runtime = (theme.directory / "site.js").read_text(encoding="utf-8")
    (version_dir / "site.js").write_text(
        (
            f"const SITE_CONFIGURATION = {_json_for_script(config)};\n"
            f"const DOCS = {_json_for_script({'groups': navigation})};\n"
            f"{site_runtime.rstrip()}\n"
        ),
        encoding="utf-8",
    )
    (version_dir / "search.js").write_text(
        f"const SEARCH_INDEX = {_json_for_script(search_index)};\n",
        encoding="utf-8",
    )
    assets_dir = theme.directory / "assets"
    if assets_dir.exists():
        shutil.copytree(assets_dir, version_dir / "assets", dirs_exist_ok=True)


def _write_note_pages(
    notes: list[Note],
    *,
    version_dir: Path,
    config: dict[str, object],
    include_folder: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    note_pages: list[dict[str, object]] = []
    search_index: list[dict[str, object]] = []
    for note in notes:
        source_path = note_file_path(note)
        if not source_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f'Cannot publish "{note.title}" because its Markdown file no longer exists '
                    "in the filesystem."
                ),
            )
        body = _without_duplicate_title_heading(
            markdown_note_body(source_path.read_text(encoding="utf-8")),
            note.title,
        )
        relative_path = Path(_published_note_path(note, include_folder=include_folder))
        page_path = version_dir / relative_path
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            _render_published_page(
                note=note,
                config=config,
                relative_path=relative_path,
                content_html=_markdown_to_html(body),
            ),
            encoding="utf-8",
        )
        path = relative_path.as_posix()
        note_pages.append(
            {
                "title": note.title,
                "path": path,
                "folder": note.folder.name,
            }
        )
        search_index.append(
            {
                "section": note.folder.name,
                "folder": note.folder.name,
                "title": note.title,
                "path": path,
                "text": _compact_text(body),
            }
        )
    return note_pages, search_index


def _render_published_page(
    *,
    note: Note,
    config: dict[str, object],
    relative_path: Path,
    content_html: str,
) -> str:
    depth = len(relative_path.parts) - 1
    version_prefix = "../" * depth
    root_prefix = "../" * (depth + 1)
    brand = str(config.get("brand") or "mianotes")
    footer_html = str(config.get("footerHtml") or "")
    return _html_shell(
        title=f"{note.title} | {brand}",
        stylesheet=f"{version_prefix}styles.css" if version_prefix else "styles.css",
        navigation_script=f"{root_prefix}navigation.js",
        search_script=f"{version_prefix}search.js" if version_prefix else "search.js",
        site_script=f"{version_prefix}site.js" if version_prefix else "site.js",
        body=(
            "<header data-header></header>\n"
            '<main class="layout">\n'
            '  <aside class="sidebar" data-sidebar></aside>\n'
            '  <section class="article-wrap">\n'
            '    <article class="article">\n'
            f'      <p class="eyebrow">{html.escape(note.folder.name)}</p>\n'
            f"      <h1>{html.escape(note.title)}</h1>\n"
            f"      {content_html}\n"
            '      <nav class="article-footer" data-article-footer></nav>\n'
            f'      <footer class="site-footer">{footer_html}</footer>\n'
            "    </article>\n"
            "  </section>\n"
            '  <aside class="page-toc" data-page-toc></aside>\n'
            "</main>\n"
        ),
    )


def _write_version_index(
    *,
    version_dir: Path,
    config: dict[str, object],
    note_pages: list[dict[str, object]],
) -> None:
    brand = html.escape(str(config.get("brand") or "mianotes"))
    first_path = str(note_pages[0]["path"]) if note_pages else ""
    if first_path:
        body = f'<a href="./{html.escape(first_path)}">Open documentation</a>'
        refresh = f'    <meta http-equiv="refresh" content="0; url=./{html.escape(first_path)}">\n'
    else:
        body = "<p>No notes were published.</p>"
        refresh = ""
    (version_dir / "index.html").write_text(
        (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "  <head>\n"
            '    <meta charset="utf-8">\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"    {GENERATOR_META_TAG}\n"
            f"{refresh}"
            f"    <title>{brand} documentation</title>\n"
            "  </head>\n"
            f"  <body>{body}</body>\n"
            "</html>\n"
        ),
        encoding="utf-8",
    )


def _write_root_index(*, html_root: Path, version_slug: str) -> None:
    html_root.mkdir(parents=True, exist_ok=True)
    (html_root / "index.html").write_text(
        (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "  <head>\n"
            '    <meta charset="utf-8">\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"    {GENERATOR_META_TAG}\n"
            "    <title>mianotes documentation</title>\n"
            '    <script src="./navigation.js"></script>\n'
            "    <script>\n"
            "      const latestPath = `./${SITE_NAVIGATION.latest}/index.html`;\n"
            "      window.location.replace(latestPath);\n"
            "    </script>\n"
            "  </head>\n"
            f'  <body><a id="latest-link" href="./{html.escape(version_slug)}/index.html">'
            "Latest version</a><script>"
            "document.getElementById('latest-link').href = latestPath;"
            "</script>"
            "</body>\n"
            "</html>\n"
        ),
        encoding="utf-8",
    )


def _write_navigation_js(
    *,
    session: Session,
    html_root: Path,
    current_site: PublishedSite,
) -> None:
    entries = _site_navigation_entries(
        session.scalars(select(PublishedSite).order_by(PublishedSite.created_at.desc())).all()
    )
    if not entries:
        entries = [
            {
                "label": f"{_site_brand(current_site)} {current_site.version}",
                "path": f"{_version_slug(current_site.version)}/index.html",
                "key": _version_slug(current_site.version),
            }
        ]
    payload = {"latest": entries[0]["key"], "navigation": entries}
    (html_root / "navigation.js").write_text(
        f"const SITE_NAVIGATION = {_json_for_script(payload)};\n",
        encoding="utf-8",
    )


def _site_navigation_entries(sites: Iterable[PublishedSite]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for site in sites:
        version_slug = _version_slug(site.version)
        if version_slug in seen:
            continue
        seen.add(version_slug)
        label = f"{_site_brand(site)} {site.version}" if not entries else site.version
        entries.append(
            {
                "label": label,
                "path": f"{version_slug}/index.html",
                "key": version_slug,
            }
        )
    return entries


def _site_brand(site: PublishedSite) -> str:
    configuration = _load_json_object(site.site_configuration, DEFAULT_SITE_CONFIGURATION)
    return str(configuration.get("brand") or "mianotes")


def _html_shell(
    *,
    title: str,
    stylesheet: str,
    navigation_script: str,
    search_script: str,
    site_script: str,
    body: str,
) -> str:
    escaped_title = html.escape(title)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"    {GENERATOR_META_TAG}\n"
        f"    <title>{escaped_title}</title>\n"
        f'    <link rel="stylesheet" href="{html.escape(stylesheet)}">\n'
        f'    <script src="{html.escape(navigation_script)}" defer></script>\n'
        f'    <script src="{html.escape(search_script)}" defer></script>\n'
        f'    <script src="{html.escape(site_script)}" defer></script>\n'
        "  </head>\n"
        f"  <body>\n{body}  </body>\n"
        "</html>\n"
    )


def _compact_text(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*_`~-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2).replace("</", "<\\/")


def _markdown_to_html(markdown: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    in_code = False
    code_lines: list[str] = []
    code_language = ""
    lines = markdown.splitlines()
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{_inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            blocks.append(f"<ul>{''.join(list_items)}</ul>")
            list_items.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append(_code_block_to_html(chr(10).join(code_lines), code_language))
                in_code = False
                code_lines.clear()
                code_language = ""
            else:
                flush_paragraph()
                flush_list()
                in_code = True
                code_language = stripped.removeprefix("```").strip()
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if not stripped:
            flush_paragraph()
            flush_list()
            index += 1
            continue
        if _is_table_start(lines, index):
            flush_paragraph()
            flush_list()
            table_lines = [line]
            index += 2
            while index < len(lines) and _is_table_row(lines[index]):
                table_lines.append(lines[index])
                index += 1
            blocks.append(_table_to_html(table_lines))
            continue
        if _is_admonition_start(stripped):
            flush_paragraph()
            flush_list()
            admonition_lines = [line]
            index += 1
            while index < len(lines) and lines[index].strip().startswith(">"):
                admonition_lines.append(lines[index])
                index += 1
            blocks.append(_admonition_to_html(admonition_lines))
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>")
            index += 1
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            flush_paragraph()
            list_items.append(f"<li>{_inline_markdown(bullet.group(1))}</li>")
            index += 1
            continue
        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    flush_list()
    if in_code:
        blocks.append(_code_block_to_html(chr(10).join(code_lines), code_language))
    return "\n".join(blocks)


def _without_duplicate_title_heading(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    first_content_index = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_content_index is None:
        return markdown.strip()

    match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", lines[first_content_index].strip())
    if not match:
        return markdown.strip()
    if _normalised_heading_text(match.group(1)) != _normalised_heading_text(title):
        return markdown.strip()
    return "\n".join(lines[first_content_index + 1 :]).strip()


def _normalised_heading_text(value: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", value)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_~]+", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _is_table_start(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and _is_table_row(lines[index])
        and _is_table_separator(lines[index + 1])
    )


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and stripped.startswith("|") and stripped.endswith("|")


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if not _is_table_row(stripped):
        return False
    cells = _table_cells(stripped)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    cell: list[str] = []
    index = 0
    while index < len(stripped):
        char = stripped[index]
        if char == "\\" and index + 1 < len(stripped) and stripped[index + 1] == "|":
            cell.append("|")
            index += 2
            continue
        if char == "|":
            cells.append("".join(cell).strip())
            cell.clear()
            index += 1
            continue
        cell.append(char)
        index += 1
    cells.append("".join(cell).strip())
    return cells


def _table_to_html(lines: list[str]) -> str:
    header_cells = _table_cells(lines[0])
    body_rows = [_table_cells(line) for line in lines[1:]]
    column_count = max(len(header_cells), *(len(row) for row in body_rows), 1)

    def padded(cells: list[str]) -> list[str]:
        return cells + [""] * (column_count - len(cells))

    header_html = "".join(
        f"<th>{_inline_markdown(cell)}</th>" for cell in padded(header_cells)
    )
    body_html = "".join(
        "<tr>"
        + "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in padded(row))
        + "</tr>"
        for row in body_rows
    )
    columns_html = "".join("<col>" for _ in range(column_count))
    return (
        '<table class="doc-table">'
        f"<colgroup>{columns_html}</colgroup>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table>"
    )


def _code_block_to_html(code: str, language: str = "") -> str:
    language_class = f' class="language-{html.escape(language)}"' if language else ""
    return (
        '<div class="code-card">'
        f"<pre><code{language_class}>{_highlight_code(code)}</code></pre>"
        "</div>"
    )


def _highlight_code(code: str) -> str:
    escaped = html.escape(code)
    escaped = re.sub(
        r"(&quot;[^&]*&quot;)(\s*:)",
        r'<span class="tok-key">\1</span>\2',
        escaped,
    )
    escaped = re.sub(
        r"(:\s*)(&quot;[^&]*&quot;)",
        r'\1<span class="tok-string">\2</span>',
        escaped,
    )
    return escaped


def _is_admonition_start(stripped: str) -> bool:
    return bool(re.match(r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", stripped, re.I))


def _admonition_to_html(lines: list[str]) -> str:
    first = lines[0].strip()
    match = re.match(
        r"^>\s*\[!(?P<kind>NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(?P<title>.*)$",
        first,
        re.I,
    )
    kind = (match.group("kind") if match else "note").lower()
    title = (match.group("title") if match else "").strip() or _admonition_default_title(kind)
    body_lines = [_strip_blockquote_marker(line) for line in lines[1:]]
    body = _markdown_to_html("\n".join(body_lines).strip()) if body_lines else ""
    return (
        f'<aside class="admonition admonition-{html.escape(kind)}">'
        f'<div class="admonition-title"><span class="admonition-icon" aria-hidden="true"></span>'
        f"<strong>{_inline_markdown(title)}</strong></div>"
        f'<div class="admonition-body">{body}</div>'
        "</aside>"
    )


def _strip_blockquote_marker(line: str) -> str:
    return re.sub(r"^>\s?", "", line)


def _admonition_default_title(kind: str) -> str:
    return {
        "note": "Note",
        "tip": "Tip",
        "important": "Important",
        "warning": "Warning",
        "caution": "Caution",
    }.get(kind, "Note")


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a class="inline-link" href="\2">\1</a>',
        escaped,
    )
    return escaped


def _default_site_configuration(theme: PublishTheme) -> dict[str, object]:
    configuration = json.loads(json.dumps(DEFAULT_SITE_CONFIGURATION))
    configuration["version"] = theme.version
    return configuration


def _load_json_object(value: str, fallback: dict[str, object]) -> dict[str, object]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return json.loads(json.dumps(fallback))
    if not isinstance(loaded, dict):
        return json.loads(json.dumps(fallback))
    merged = json.loads(json.dumps(fallback))
    merged.update(loaded)
    return merged


def _load_json_list(value: str, fallback: list[dict[str, object]]) -> list[dict[str, object]]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return json.loads(json.dumps(fallback))
    if not isinstance(loaded, list):
        return json.loads(json.dumps(fallback))
    return [item for item in loaded if isinstance(item, dict)]


def _version_slug(version: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", version.strip()).strip(".-_")
    return slug or "site"
