from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import TagsReadUser
from mianotes_web_service.db.models import Tag
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import TagRead

router = APIRouter(prefix="/tags", tags=["tags"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[TagRead])
def list_tags(session: SessionDep, user: TagsReadUser) -> list[Tag]:
    return list(session.scalars(select(Tag).order_by(Tag.name)))
