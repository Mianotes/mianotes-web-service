from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import FoldersReadUser, FoldersWriteUser
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Folder
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import FolderCreate, FolderRead, FolderUpdate
from mianotes_web_service.services.storage import slugify

router = APIRouter(prefix="/folders", tags=["folders"])
SessionDep = Annotated[Session, Depends(get_session)]


def _read_folder_or_404(session: Session, folder_id: str) -> Folder:
    folder = session.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return folder


@router.post("", response_model=FolderRead, status_code=status.HTTP_201_CREATED)
def create_folder(payload: FolderCreate, session: SessionDep, user: FoldersWriteUser) -> Folder:
    slug = slugify(payload.name)
    folder = Folder(
        user_id=user.id,
        name=payload.name,
        slug=slug,
        path=slug,
        is_pinned=payload.is_pinned,
    )
    session.add(folder)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A folder with this name already exists",
        ) from exc
    session.refresh(folder)
    return folder


@router.get("", response_model=list[FolderRead])
def list_folders(
    session: SessionDep,
    user: FoldersReadUser,
    user_id: Annotated[str | None, Query()] = None,
    include_archived: Annotated[bool, Query()] = False,
) -> list[Folder]:
    statement = select(Folder).order_by(Folder.is_pinned.desc(), Folder.created_at.desc())
    if user_id is not None:
        statement = statement.where(Folder.user_id == user_id)
    if not include_archived:
        statement = statement.where(Folder.archived_at.is_(None))
    return list(session.scalars(statement))


@router.get("/{folder_id}", response_model=FolderRead)
def get_folder(folder_id: str, session: SessionDep, user: FoldersReadUser) -> Folder:
    return _read_folder_or_404(session, folder_id)


@router.patch("/{folder_id}", response_model=FolderRead)
def update_folder(
    folder_id: str,
    payload: FolderUpdate,
    session: SessionDep,
    user: FoldersWriteUser,
) -> Folder:
    folder = _read_folder_or_404(session, folder_id)
    if not user.is_admin and folder.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change this folder",
        )
    if folder.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    if payload.name is not None:
        next_slug = slugify(payload.name)
        if next_slug != folder.slug:
            existing = session.scalars(
                select(Folder).where(Folder.slug == next_slug, Folder.id != folder.id)
            ).one_or_none()
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A folder with this name already exists",
                )
            data_dir = get_settings().data_dir
            old_path = data_dir / folder.path
            new_path = data_dir / next_slug
            if new_path.exists() and old_path.resolve() != new_path.resolve():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A folder with this name already exists",
                )
            if old_path.exists():
                old_path.rename(new_path)
        folder.name = payload.name
        folder.slug = next_slug
        folder.path = next_slug
    if payload.is_pinned is not None:
        folder.is_pinned = payload.is_pinned

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A folder with this name already exists",
        ) from exc
    session.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_folder(folder_id: str, session: SessionDep, user: FoldersWriteUser) -> None:
    folder = _read_folder_or_404(session, folder_id)
    if not user.is_admin and folder.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot archive this folder",
        )
    folder.archived_at = datetime.now(UTC)
    folder.archived_by_user_id = user.id
    session.commit()
