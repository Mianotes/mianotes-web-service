from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import AdminUser, CurrentUser, UsersReadUser
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
def create_user(payload: UserCreate, session: SessionDep, user: AdminUser) -> User:
    email = str(payload.email).lower()
    created_user = User(
        email=email,
        name=payload.name,
        username=make_username(email, payload.name),
        phone=payload.phone,
        role=payload.role,
    )
    session.add(created_user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from exc
    session.refresh(created_user)
    return created_user


@router.get("", response_model=list[UserRead])
def list_users(session: SessionDep, user: UsersReadUser) -> list[User]:
    return list(session.scalars(select(User).order_by(User.created_at.desc())))


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: str, session: SessionDep, user: UsersReadUser) -> User:
    return _read_user_or_404(session, user_id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: UserUpdate, session: SessionDep, user: CurrentUser) -> User:
    target_user = _read_user_or_404(session, user_id)
    if not user.is_admin and user.id != target_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update other user profiles",
        )
    if payload.name is not None:
        target_user.name = payload.name
    if payload.email is not None:
        email = str(payload.email).lower()
        target_user.email = email
        target_user.username = make_username(email, payload.name or target_user.name)
    if payload.phone is not None:
        target_user.phone = payload.phone
    if payload.role is not None:
        target_user.role = payload.role
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from exc
    session.refresh(target_user)
    return target_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, session: SessionDep, user: AdminUser) -> None:
    user = _read_user_or_404(session, user_id)
    session.delete(user)
    session.commit()
