from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Note, Tag
from mianotes_web_service.domain.schemas import MAX_TAGS_PER_NOTE
from mianotes_web_service.services.storage import slugify


def sync_note_tags(session: Session, note: Note, tag_names: list[str]) -> None:
    normalized_names: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in tag_names:
        normalized = " ".join(name.strip().split())
        if not normalized:
            continue
        slug = slugify(normalized)
        if slug in seen:
            continue
        seen.add(slug)
        normalized_names.append((normalized, slug))

    if len(normalized_names) > MAX_TAGS_PER_NOTE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A note can have at most {MAX_TAGS_PER_NOTE} tags",
        )

    tags: list[Tag] = []
    for normalized, slug in normalized_names:
        tag = session.scalars(select(Tag).where(Tag.slug == slug)).one_or_none()
        if tag is None:
            tag = Tag(name=normalized, slug=slug)
            session.add(tag)
            session.flush()
        tags.append(tag)
    note.tags = tags
