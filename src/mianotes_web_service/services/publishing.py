from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Note, PublishedSite, User
from mianotes_web_service.domain.schemas import PublishRequest
from mianotes_web_service.services.paths import WorkspacePaths, workspace_paths_for_session
from mianotes_web_service.services.publishing_draft import (
    PUBLISHABLE_NOTE_STATUSES as PUBLISHABLE_NOTE_STATUSES,
)
from mianotes_web_service.services.publishing_draft import (
    PublishDraft as PublishDraft,
)
from mianotes_web_service.services.publishing_draft import (
    build_publish_draft as build_publish_draft,
)
from mianotes_web_service.services.publishing_draft import (
    read_folder,
    read_publishable_notes,
    read_tag,
)
from mianotes_web_service.services.publishing_history import (
    version_slug,
    write_navigation_js,
    write_root_index,
)
from mianotes_web_service.services.publishing_navigation import (
    navigation_paths_in_order,
    published_note_path,
)
from mianotes_web_service.services.publishing_static import (
    write_note_pages,
    write_version_index,
)
from mianotes_web_service.services.publishing_theme import (
    DEFAULT_SITE_CONFIGURATION as DEFAULT_SITE_CONFIGURATION,
)
from mianotes_web_service.services.publishing_theme import (
    GENERATOR_META_TAG as GENERATOR_META_TAG,
)
from mianotes_web_service.services.publishing_theme import (
    THEMES_DIR as THEMES_DIR,
)
from mianotes_web_service.services.publishing_theme import (
    PublishTheme as PublishTheme,
)
from mianotes_web_service.services.publishing_theme import (
    list_publish_themes as list_publish_themes,
)
from mianotes_web_service.services.publishing_theme import (
    read_publish_theme,
    write_theme_assets,
)


def publish_site(session: Session, user: User, payload: PublishRequest) -> PublishedSite:
    theme = read_publish_theme(payload.theme)
    folder = read_folder(session, payload.folder_id) if payload.folder_id else None
    tag = read_tag(session, payload.tag_id) if payload.tag_id else None
    notes = read_publishable_notes(session, folder_id=payload.folder_id, tag_id=payload.tag_id)
    include_folder = payload.folder_id is None
    notes_by_path = {
        published_note_path(note, include_folder=include_folder): note for note in notes
    }
    notes = [
        notes_by_path[path]
        for path in navigation_paths_in_order(payload.navigation)
        if path in notes_by_path
    ]
    version = str(payload.site_configuration.get("version") or theme.version)
    next_version_slug = version_slug(version)
    paths = workspace_paths_for_session(session)
    data_dir = paths.data_dir
    html_root = data_dir / "html"
    version_dir = html_root / next_version_slug
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True, exist_ok=True)

    note_pages, search_index = write_note_pages(
        notes,
        version_dir=version_dir,
        config=payload.site_configuration,
        include_folder=include_folder,
        paths=paths,
    )
    write_theme_assets(
        theme,
        version_dir=version_dir,
        config=payload.site_configuration,
        navigation=payload.navigation,
        search_index=search_index,
    )
    write_version_index(
        version_dir=version_dir,
        config=payload.site_configuration,
        note_pages=note_pages,
    )
    write_root_index(html_root=html_root, version_slug=next_version_slug)
    markdown_paths_by_html_path = markdown_paths_for_readme(
        notes,
        include_folder=include_folder,
        data_dir=data_dir,
        paths=paths,
    )

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
        html_path=f"html/{next_version_slug}",
        markdown_path="",
        url_path=f"html/{next_version_slug}/index.html",
        site_configuration=json.dumps(payload.site_configuration),
        navigation=json.dumps(payload.navigation),
        note_count=len(notes),
    )
    session.add(published_site)
    session.commit()
    session.refresh(published_site)
    write_navigation_js(
        session=session,
        html_root=html_root,
        current_site=published_site,
        markdown_paths_by_html_path=markdown_paths_by_html_path,
    )
    return published_site


def markdown_paths_for_readme(
    notes: list[Note],
    *,
    include_folder: bool,
    data_dir: Path,
    paths: WorkspacePaths,
) -> dict[str, str]:
    return {
        published_note_path(note, include_folder=include_folder): markdown_path_for_readme(
            paths.note_file_path(note),
            data_dir=data_dir,
        )
        for note in notes
    }


def markdown_path_for_readme(note_path: Path, *, data_dir: Path) -> str:
    if note_path.is_absolute():
        try:
            return note_path.resolve().relative_to(data_dir.resolve()).as_posix()
        except ValueError:
            return note_path.name

    parts = note_path.parts
    if len(parts) > 1 and parts[0] == data_dir.name:
        return Path(*parts[1:]).as_posix()
    return note_path.as_posix()
