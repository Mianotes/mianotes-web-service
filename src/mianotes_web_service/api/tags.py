from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from mianotes_web_service.api.dependencies import SessionDep, TagsReadUser
from mianotes_web_service.db.models import Tag
from mianotes_web_service.domain.schemas import TagRead

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
def list_tags(session: SessionDep, user: TagsReadUser) -> list[Tag]:
    return list(session.scalars(select(Tag).order_by(Tag.name)))
