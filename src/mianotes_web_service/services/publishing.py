from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Folder, Note, PublishedSite, Tag, User
from mianotes_web_service.domain.schemas import PublishRequest
from mianotes_web_service.services.paths import note_file_path
from mianotes_web_service.services.storage import markdown_note_body, short_id, slugify

PUBLISHABLE_NOTE_STATUSES = ("ready", "published")

THEMES_DIR = Path(__file__).resolve().parents[1] / "publishing" / "themes"
DEFAULT_SITE_CONFIGURATION: dict[str, object] = {
    "brand": "mianotes",
    "version": "0.1.0",
    "headerLinks": [
        {"title": "GitHub", "url": "https://github.com/Mianotes"},
        {"title": "Contact", "url": "mailto:mianotes@proton.me"},
    ],
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
    return themes


def read_publish_theme(theme_id: str) -> PublishTheme:
    theme = next((theme for theme in list_publish_themes() if theme.id == theme_id), None)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found")
    return theme


def build_publish_draft(
    session: Session,
    *,
    theme_id: str = "mianotes",
    folder_id: str | None = None,
    tag_id: str | None = None,
) -> PublishDraft:
    theme = read_publish_theme(theme_id)
    folder = _read_folder(session, folder_id) if folder_id else None
    tag = _read_tag(session, tag_id) if tag_id else None
    notes = _read_publishable_notes(session, folder_id=folder_id, tag_id=tag_id)
    latest_publish = _read_latest_publish(session, folder_id=folder_id, tag_id=tag_id)
    since = latest_publish.created_at if latest_publish else None
    include_folder = folder_id is None
    site_configuration = (
        _load_json_object(latest_publish.site_configuration, DEFAULT_SITE_CONFIGURATION)
        if latest_publish
        else _default_site_configuration(theme)
    )
    navigation = (
        _load_json_list(latest_publish.navigation, [])
        if latest_publish
        else _navigation_for_notes(notes, include_folder=include_folder)
    )
    updated_notes = [] if since is None else _updated_notes(
        notes,
        since=since,
        include_folder=include_folder,
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
    html_dir = data_dir / "html" / version_slug
    if html_dir.exists():
        shutil.rmtree(html_dir)
    html_dir.mkdir(parents=True, exist_ok=True)
    _copy_theme_assets(theme, html_dir / "assets")

    note_pages = _write_note_pages(
        notes,
        html_dir=html_dir,
        include_folder=payload.folder_id is None,
    )
    _write_index(
        html_dir=html_dir,
        config=payload.site_configuration,
        navigation=payload.navigation,
        updated_notes=payload.updated_notes,
        note_pages=note_pages,
    )

    now = datetime.now(UTC)
    for note in notes:
        note.is_published = True
        note.published_at = now
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
    since: datetime | None,
    include_folder: bool,
) -> list[dict[str, object]]:
    return [
        {
            "title": note.title,
            "path": _published_note_path(note, include_folder=include_folder),
        }
        for note in notes
        if since is None or _as_utc(note.updated_at) > _as_utc(since)
    ]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _published_note_path(note: Note, *, include_folder: bool) -> str:
    filename = f"{slugify(note.title)}-{short_id(note.id)}.html"
    if include_folder:
        return f"{note.folder.slug}/{filename}"
    return filename


def _copy_theme_assets(theme: PublishTheme, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("styles.css", "site.js"):
        source = theme.directory / filename
        if source.exists():
            shutil.copy2(source, target_dir / filename)
    assets_dir = theme.directory / "assets"
    if assets_dir.exists():
        for source in assets_dir.iterdir():
            target = target_dir / source.name
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)


def _write_note_pages(
    notes: list[Note],
    *,
    html_dir: Path,
    include_folder: bool,
) -> list[dict[str, object]]:
    note_pages: list[dict[str, object]] = []
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
        body = markdown_note_body(source_path.read_text(encoding="utf-8"))
        relative_path = Path(_published_note_path(note, include_folder=include_folder))
        page_path = html_dir / relative_path
        nested_page = len(relative_path.parts) > 1
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            _render_page(
                title=note.title,
                content_html=_markdown_to_html(body),
                asset_prefix="../assets" if nested_page else "assets",
                index_href="../index.html" if nested_page else "index.html",
            ),
            encoding="utf-8",
        )
        note_pages.append(
            {
                "title": note.title,
                "path": relative_path.as_posix(),
                "folder": note.folder.name,
            }
        )
    return note_pages


def _write_index(
    *,
    html_dir: Path,
    config: dict[str, object],
    navigation: list[dict[str, object]],
    updated_notes: list[dict[str, object]],
    note_pages: list[dict[str, object]],
) -> None:
    brand = html.escape(str(config.get("brand") or "mianotes"))
    footer_html = str(config.get("footerHtml") or "")
    header_links = _render_header_links(config.get("headerLinks"))
    nav_html = _render_navigation(navigation)
    updated_html = _render_updated_notes(updated_notes)
    first_note = note_pages[0] if note_pages else None
    intro = (
        f'<p>Your static site contains {len(note_pages)} published notes.</p>'
        if first_note is None
        else (
            f'<p>Your static site contains {len(note_pages)} published notes. '
            f'Start with <a href="{html.escape(str(first_note["path"]))}">'
            f'{html.escape(str(first_note["title"]))}</a>.</p>'
        )
    )
    (html_dir / "index.html").write_text(
        _html_document(
            title=brand,
            asset_prefix="assets",
            body=(
                '<div class="site">'
                f'<aside class="sidebar"><h1 class="brand">{brand}</h1>{nav_html}</aside>'
                '<main class="content">'
                f"{header_links}"
                f"{updated_html}"
                f'<article class="article"><h1>{brand}</h1>{intro}</article>'
                f"<footer>{footer_html}</footer>"
                "</main></div>"
            ),
        ),
        encoding="utf-8",
    )


def _render_page(
    *,
    title: str,
    content_html: str,
    asset_prefix: str,
    index_href: str,
) -> str:
    escaped_index_href = html.escape(index_href)
    return _html_document(
        title=title,
        asset_prefix=asset_prefix,
        body=(
            '<div class="site">'
            '<aside class="sidebar"><h1 class="brand">'
            f'<a href="{escaped_index_href}">mianotes</a></h1></aside>'
            f'<main class="content"><article class="article"><h1>{html.escape(title)}</h1>'
            f"{content_html}</article></main></div>"
        ),
    )


def _html_document(*, title: str, body: str, asset_prefix: str) -> str:
    escaped_title = html.escape(title)
    escaped_asset_prefix = html.escape(asset_prefix)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{escaped_title}</title>\n"
        f'  <link rel="stylesheet" href="{escaped_asset_prefix}/styles.css">\n'
        "</head>\n"
        f'<body>{body}<script src="{escaped_asset_prefix}/site.js"></script></body>\n'
        "</html>\n"
    )


def _render_navigation(navigation: list[dict[str, object]]) -> str:
    groups: list[str] = []
    for group in navigation:
        title = html.escape(str(group.get("title") or "Notes"))
        items = group.get("items")
        links: list[str] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_title = html.escape(
                    str(item.get("title") or item.get("pageTitle") or "Untitled")
                )
                path = html.escape(str(item.get("path") or "#"))
                links.append(f'<a href="{path}">{item_title}</a>')
        groups.append(f'<section class="nav-group"><h2>{title}</h2>{"".join(links)}</section>')
    return "".join(groups)


def _render_header_links(header_links: object) -> str:
    if not isinstance(header_links, list):
        return ""
    links: list[str] = []
    for item in header_links:
        if not isinstance(item, dict):
            continue
        title = html.escape(str(item.get("title") or "Link"))
        url = html.escape(str(item.get("url") or "#"))
        links.append(f'<a href="{url}">{title}</a>')
    if not links:
        return ""
    return f'<nav class="top-links">{"".join(links)}</nav>'


def _render_updated_notes(updated_notes: list[dict[str, object]]) -> str:
    if not updated_notes:
        return ""
    items = []
    for note in updated_notes:
        title = html.escape(str(note.get("title") or "Untitled"))
        path = html.escape(str(note.get("path") or "#"))
        items.append(f'<li><a href="{path}">{title}</a></li>')
    return (
        '<section class="updated"><h2>Updated notes</h2>'
        f'<ul>{"".join(items)}</ul></section>'
    )


def _markdown_to_html(markdown: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    in_code = False
    code_lines: list[str] = []
    code_language = ""

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{_inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            blocks.append(f"<ul>{''.join(list_items)}</ul>")
            list_items.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append(
                    f'<pre><code class="language-{html.escape(code_language)}">'
                    f"{html.escape(chr(10).join(code_lines))}</code></pre>"
                )
                in_code = False
                code_lines.clear()
                code_language = ""
            else:
                flush_paragraph()
                flush_list()
                in_code = True
                code_language = stripped.removeprefix("```").strip()
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>")
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            flush_paragraph()
            list_items.append(f"<li>{_inline_markdown(bullet.group(1))}</li>")
            continue
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    if in_code:
        blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(blocks)


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
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
    return loaded


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
