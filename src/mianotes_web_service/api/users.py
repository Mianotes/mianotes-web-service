from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import UserCreate, UserRead, UserUpdate
from mianotes_web_service.services.storage import make_username

router = APIRouter(prefix="/users", tags=["users"])
SessionDep = Annotated[Session, Depends(get_session)]


def _read_user_or_404(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: SessionDep) -> User:
    email = str(payload.email).lower()
    user = User(email=email, name=payload.name, username=make_username(email))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from exc
    session.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
def list_users(session: SessionDep) -> list[User]:
    return list(session.scalars(select(User).order_by(User.created_at.desc())))


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: str, session: SessionDep) -> User:
    return _read_user_or_404(session, user_id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: UserUpdate, session: SessionDep) -> User:
    user = _read_user_or_404(session, user_id)
    if payload.name is not None:
        user.name = payload.name
    if payload.email is not None:
        email = str(payload.email).lower()
        user.email = email
        user.username = make_username(email)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from exc
    session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, session: SessionDep) -> None:
    user = _read_user_or_404(session, user_id)
    session.delete(user)
    session.commit()

