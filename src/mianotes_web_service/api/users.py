from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import AdminUser, CurrentUser, UsersReadUser
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import UserCreate, UserRead, UserUpdate
from mianotes_web_service.services.storage import make_username

router = APIRouter(prefix="/users", tags=["users"])
SessionDep = Annotated[Session, Depends(get_session)]
AVATAR_SIZE = (200, 200)
SUPPORTED_AVATAR_TYPES = {"image/jpeg", "image/png"}


def _read_user_or_404(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _ensure_can_update_profile(current_user: User, target_user: User) -> None:
    if not current_user.is_admin and current_user.id != target_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update other user profiles",
        )


def _avatar_path(user_id: str) -> Path:
    return Path(".profiles") / user_id / "avatar.jpg"


def _save_avatar(user_id: str, upload: UploadFile) -> str:
    if upload.content_type not in SUPPORTED_AVATAR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Profile photos must be JPG or PNG images",
        )
    try:
        image = Image.open(BytesIO(upload.file.read()))
        image.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read this image",
        ) from exc

    image = ImageOps.fit(image, AVATAR_SIZE, method=Image.Resampling.LANCZOS)
    if image.mode != "RGB":
        background = Image.new("RGB", image.size, "#ffffff")
        if image.mode in {"RGBA", "LA"}:
            background.paste(image, mask=image.getchannel("A"))
        else:
            background.paste(image.convert("RGB"))
        image = background

    relative_path = _avatar_path(user_id)
    target = get_settings().data_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="JPEG", quality=90, optimize=True)
    return relative_path.as_posix()


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
    _ensure_can_update_profile(user, target_user)
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


@router.post("/{user_id}/photo", response_model=UserRead)
def upload_user_photo(
    user_id: str,
    photo: Annotated[UploadFile, File()],
    session: SessionDep,
    user: CurrentUser,
) -> User:
    target_user = _read_user_or_404(session, user_id)
    _ensure_can_update_profile(user, target_user)
    target_user.avatar_path = _save_avatar(target_user.id, photo)
    session.commit()
    session.refresh(target_user)
    return target_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, session: SessionDep, user: AdminUser) -> None:
    user = _read_user_or_404(session, user_id)
    session.delete(user)
    session.commit()
