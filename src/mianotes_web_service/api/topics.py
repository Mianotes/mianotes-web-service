from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Topic, User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import TopicCreate, TopicRead, TopicUpdate
from mianotes_web_service.services.storage import slugify

router = APIRouter(prefix="/topics", tags=["topics"])
SessionDep = Annotated[Session, Depends(get_session)]


def _read_topic_or_404(session: Session, topic_id: str) -> Topic:
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic


@router.post("", response_model=TopicRead, status_code=status.HTTP_201_CREATED)
def create_topic(payload: TopicCreate, session: SessionDep) -> Topic:
    if session.get(User, payload.user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    topic = Topic(user_id=payload.user_id, name=payload.name, slug=slugify(payload.name))
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
    user_id: Annotated[str | None, Query()] = None,
) -> list[Topic]:
    statement = select(Topic).order_by(Topic.created_at.desc())
    if user_id is not None:
        statement = statement.where(Topic.user_id == user_id)
    return list(session.scalars(statement))


@router.get("/{topic_id}", response_model=TopicRead)
def get_topic(topic_id: str, session: SessionDep) -> Topic:
    return _read_topic_or_404(session, topic_id)


@router.patch("/{topic_id}", response_model=TopicRead)
def update_topic(topic_id: str, payload: TopicUpdate, session: SessionDep) -> Topic:
    topic = _read_topic_or_404(session, topic_id)
    topic.name = payload.name
    topic.slug = slugify(payload.name)
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


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(topic_id: str, session: SessionDep) -> None:
    topic = _read_topic_or_404(session, topic_id)
    session.delete(topic)
    session.commit()

