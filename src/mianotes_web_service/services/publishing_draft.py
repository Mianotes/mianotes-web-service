from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.db.models import Folder, Note, PublishedSite, Tag
from mianotes_web_service.services.publishing_navigation import (
    navigation_for_notes,
    navigation_paths,
    navigation_with_new_notes,
    updated_notes,
)
from mianotes_web_service.services.publishing_theme import (
    default_site_configuration,
    read_publish_theme,
)

PUBLISHABLE_NOTE_STATUSES = ("ready", "published")


@dataclass(frozen=True)
class PublishDraft:
    theme: str
    folder_id: str | None
    tag_id: str | None
    site_configuration: dict[str, object]
    navigation: list[dict[str, object]]
    updated_notes: list[dict[str, object]]
    generated_at: datetime


def build_publish_draft(
    session: Session,
    *,
    theme_id: str = "mialight",
    folder_id: str | None = None,
    tag_id: str | None = None,
) -> PublishDraft:
    theme = read_publish_theme(theme_id)
    folder = read_folder(session, folder_id) if folder_id else None
    tag = read_tag(session, tag_id) if tag_id else None
    notes = read_publishable_notes(session, folder_id=folder_id, tag_id=tag_id)
    latest_publish = read_latest_publish(session, folder_id=folder_id, tag_id=tag_id)
    has_previous_publish = latest_publish is not None
    include_folder = folder_id is None
    default_configuration = default_site_configuration(theme)
    site_configuration = (
        load_json_object(latest_publish.site_configuration, default_configuration)
        if latest_publish
        else default_configuration
    )
    previous_navigation = load_json_list(latest_publish.navigation, []) if latest_publish else []
    navigation = (
        navigation_with_new_notes(
            previous_navigation,
            notes,
            include_folder=include_folder,
            since=latest_publish.created_at,
        )
        if latest_publish
        else navigation_for_notes(notes, include_folder=include_folder)
    )
    previous_navigation_paths = navigation_paths(previous_navigation) if latest_publish else set()
    changed_notes = (
        []
        if not has_previous_publish
        else updated_notes(
            notes,
            include_folder=include_folder,
            previous_navigation_paths=previous_navigation_paths,
            since=latest_publish.created_at,
        )
    )
    return PublishDraft(
        theme=theme.id,
        folder_id=folder.id if folder else None,
        tag_id=tag.id if tag else None,
        site_configuration=site_configuration,
        navigation=navigation,
        updated_notes=changed_notes,
        generated_at=datetime.now(UTC),
    )


def read_folder(session: Session, folder_id: str | None) -> Folder:
    folder = session.get(Folder, folder_id)
    if folder is None or folder.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return folder


def read_tag(session: Session, tag_id: str | None) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


def read_publishable_notes(
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
        .order_by(
            Folder.is_pinned.desc(),
            Folder.sort_order.asc(),
            Folder.created_at.desc(),
            Note.title.asc(),
        )
    )
    if folder_id:
        statement = statement.where(Note.folder_id == folder_id)
    if tag_id:
        statement = statement.where(Note.tags.any(Tag.id == tag_id))
    return list(session.scalars(statement).unique())


def read_latest_publish(
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


def load_json_object(value: str, fallback: dict[str, object]) -> dict[str, object]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return json.loads(json.dumps(fallback))
    if not isinstance(loaded, dict):
        return json.loads(json.dumps(fallback))
    merged = json.loads(json.dumps(fallback))
    merged.update(loaded)
    return merged


def load_json_list(value: str, fallback: list[dict[str, object]]) -> list[dict[str, object]]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return json.loads(json.dumps(fallback))
    if not isinstance(loaded, list):
        return json.loads(json.dumps(fallback))
    return [item for item in loaded if isinstance(item, dict)]
