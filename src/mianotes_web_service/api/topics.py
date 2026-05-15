from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import TopicsReadUser, TopicsWriteUser
from mianotes_web_service.db.models import Topic
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import TopicCreate, TopicRead
from mianotes_web_service.services.storage import slugify

router = APIRouter(prefix="/topics", tags=["topics"])
SessionDep = Annotated[Session, Depends(get_session)]


def _read_topic_or_404(session: Session, topic_id: str) -> Topic:
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic


@router.post("", response_model=TopicRead, status_code=status.HTTP_201_CREATED)
def create_topic(payload: TopicCreate, session: SessionDep, user: TopicsWriteUser) -> Topic:
    topic = Topic(user_id=user.id, name=payload.name, slug=slugify(payload.name))
    session.add(topic)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A topic with this name already exists for this user",
        ) from exc
    session.refresh(topic)
    return topic


@router.get("", response_model=list[TopicRead])
def list_topics(
    session: SessionDep,
    user: TopicsReadUser,
    user_id: Annotated[str | None, Query()] = None,
    include_archived: Annotated[bool, Query()] = False,
) -> list[Topic]:
    statement = select(Topic).order_by(Topic.created_at.desc())
    if user_id is not None:
        statement = statement.where(Topic.user_id == user_id)
    if not include_archived:
        statement = statement.where(Topic.archived_at.is_(None))
    return list(session.scalars(statement))


@router.get("/{topic_id}", response_model=TopicRead)
def get_topic(topic_id: str, session: SessionDep, user: TopicsReadUser) -> Topic:
    return _read_topic_or_404(session, topic_id)


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_topic(topic_id: str, session: SessionDep, user: TopicsWriteUser) -> None:
    topic = _read_topic_or_404(session, topic_id)
    if not user.is_admin and topic.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot archive this topic",
        )
    topic.archived_at = datetime.now(UTC)
    topic.archived_by_user_id = user.id
    session.commit()
