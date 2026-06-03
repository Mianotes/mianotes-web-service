from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import FoldersReadUser, FoldersWriteUser
from mianotes_web_service.db.models import Folder, Note, PublishedSite
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import (
    FolderCreate,
    FolderNoteCounts,
    FolderRead,
    FolderReorder,
    FolderRestore,
    FolderUpdate,
)
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.storage import short_id, slugify

router = APIRouter(prefix="/folders", tags=["folders"])
SessionDep = Annotated[Session, Depends(get_session)]


def _read_folder_or_404(session: Session, folder_id: str) -> Folder:
    folder = session.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return folder


def _folder_slug_exists(session: Session, slug: str, folder_id: str | None = None) -> bool:
    statement = select(Folder).where(Folder.slug == slug)
    if folder_id is not None:
        statement = statement.where(Folder.id != folder_id)
    return session.scalars(statement).first() is not None


def _unique_folder_slug(session: Session, slug: str, folder_id: str) -> str:
    if not _folder_slug_exists(session, slug, folder_id):
        return slug

    base_candidate = f"{slug}-{short_id(folder_id)}"
    if not _folder_slug_exists(session, base_candidate, folder_id):
        return base_candidate

    index = 2
    candidate = f"{base_candidate}-{index}"
    while _folder_slug_exists(session, candidate, folder_id):
        index += 1
        candidate = f"{base_candidate}-{index}"
    return candidate


def _ensure_folder_gitignore(folder_path: Path) -> None:
    gitignore_path = folder_path / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text("sources/*\n", encoding="utf-8")


def _replace_path_prefix(value: str, old_roots: tuple[Path, ...], new_root: Path) -> str:
    path = Path(value)
    for old_root in old_roots:
        try:
            return str(new_root / path.relative_to(old_root))
        except ValueError:
            old_text = str(old_root)
            if value.startswith(old_text):
                return str(new_root) + value[len(old_text) :]
    return value


def _remove_stale_archived_folder(session: Session, folder: Folder) -> None:
    for site in session.scalars(select(PublishedSite).where(PublishedSite.folder_id == folder.id)):
        site.folder_id = None
    session.delete(folder)
    session.commit()


def _folder_order_statement():
    return select(Folder).order_by(
        Folder.is_pinned.desc(),
        Folder.sort_order.asc(),
        Folder.created_at.desc(),
    )


def _next_folder_sort_order(session: Session, user_id: str) -> int:
    current = session.scalar(
        select(func.max(Folder.sort_order)).where(
            Folder.user_id == user_id,
            Folder.archived_at.is_(None),
        )
    )
    return (current or 0) + 10


@router.post("", response_model=FolderRead, status_code=status.HTTP_201_CREATED)
def create_folder(payload: FolderCreate, session: SessionDep, user: FoldersWriteUser) -> Folder:
    slug = slugify(payload.name)
    folder = Folder(
        user_id=user.id,
        name=payload.name,
        slug=slug,
        path=slug,
        is_pinned=payload.is_pinned,
        sort_order=_next_folder_sort_order(session, user.id),
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
    statement = _folder_order_statement()
    if user_id is not None:
        statement = statement.where(Folder.user_id == user_id)
    if not include_archived:
        statement = statement.where(Folder.archived_at.is_(None))
    return list(session.scalars(statement))


@router.get("/counts", response_model=FolderNoteCounts)
def list_folder_note_counts(session: SessionDep, user: FoldersReadUser) -> FolderNoteCounts:
    rows = session.execute(select(Note.folder_id, func.count(Note.id)).group_by(Note.folder_id))
    return FolderNoteCounts(
        folders={folder_id: count for folder_id, count in rows if folder_id is not None}
    )


@router.patch("/order", response_model=list[FolderRead])
def reorder_folders(
    payload: FolderReorder,
    session: SessionDep,
    user: FoldersWriteUser,
) -> list[Folder]:
    folder_ids = payload.folder_ids
    if len(set(folder_ids)) != len(folder_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder order cannot contain duplicate folders",
        )

    folders = list(session.scalars(select(Folder).where(Folder.id.in_(folder_ids))))
    folders_by_id = {folder.id: folder for folder in folders}
    if len(folders_by_id) != len(folder_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    for folder in folders_by_id.values():
        if folder.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        if not user.is_admin and folder.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the folder owner or an admin can sort this folder",
            )
        if folder.is_pinned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pinned folders must be unpinned before sorting",
            )

    for index, folder_id in enumerate(folder_ids, start=1):
        folders_by_id[folder_id].sort_order = index * 10

    session.commit()
    return list(session.scalars(_folder_order_statement().where(Folder.archived_at.is_(None))))


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
            detail="Only the folder owner or an admin can change this folder",
        )
    if folder.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    if payload.name is not None:
        next_slug = slugify(payload.name)
        if next_slug != folder.slug:
            paths = workspace_paths_for_session(session)
            existing = session.scalars(
                select(Folder).where(Folder.slug == next_slug, Folder.id != folder.id)
            ).one_or_none()
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A folder with this name already exists",
                )
            old_path = paths.folder_directory(folder)
            new_path = paths.markdown_root / next_slug
            if new_path.exists() and old_path.resolve() != new_path.resolve():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A folder with this name already exists",
                )
            if old_path.exists():
                old_path.rename(new_path)
                _ensure_folder_gitignore(new_path)
                for note in folder.notes:
                    note.note_path = _replace_path_prefix(note.note_path, (old_path,), new_path)
                    for source_file in note.source_files:
                        source_file.file_path = _replace_path_prefix(
                            source_file.file_path, (old_path,), new_path
                        )
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


@router.post("/{folder_id}/restore", response_model=FolderRead)
def restore_folder(
    folder_id: str,
    session: SessionDep,
    user: FoldersWriteUser,
    payload: Annotated[FolderRestore | None, Body()] = None,
) -> Folder:
    folder = _read_folder_or_404(session, folder_id)
    if not user.is_admin and folder.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the folder owner or an admin can restore this folder",
        )
    if folder.archived_at is None:
        return folder

    payload = payload or FolderRestore()
    paths = workspace_paths_for_session(session)
    restore_name = payload.name or folder.name
    restore_slug = _unique_folder_slug(session, slugify(restore_name), folder.id)
    archived_path = paths.folder_directory(folder)
    restored_path = paths.markdown_root / restore_slug
    previous_live_path = paths.markdown_root / slugify(folder.name)

    if not archived_path.exists():
        _remove_stale_archived_folder(session, folder)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archived folder no longer exists in the filesystem",
        )
    if restored_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A folder with this name already exists",
        )

    restored_path.parent.mkdir(parents=True, exist_ok=True)
    archived_path.rename(restored_path)
    _ensure_folder_gitignore(restored_path)

    old_roots = (archived_path, previous_live_path)
    for note in folder.notes:
        note.note_path = _replace_path_prefix(note.note_path, old_roots, restored_path)
        for source_file in note.source_files:
            source_file.file_path = _replace_path_prefix(
                source_file.file_path,
                old_roots,
                restored_path,
            )

    folder.name = restore_name
    folder.slug = restore_slug
    folder.path = restore_slug
    folder.archived_at = None
    folder.archived_by_user_id = None
    if payload.is_pinned is not None:
        folder.is_pinned = payload.is_pinned

    session.commit()
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
    if folder.archived_at is not None:
        return

    archived_at = datetime.now(UTC)
    paths = workspace_paths_for_session(session)
    archive_slug = f"{folder.slug}-{short_id(folder.id)}"
    archive_path = f".archived/{archive_slug}"
    old_path = paths.folder_directory(folder)
    new_path = paths.markdown_root / archive_path

    if old_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.rename(new_path)

        for note in folder.notes:
            note.note_path = _replace_path_prefix(note.note_path, (old_path,), new_path)
            for source_file in note.source_files:
                source_file.file_path = _replace_path_prefix(
                    source_file.file_path,
                    (old_path,),
                    new_path,
                )

    folder.slug = archive_slug
    folder.path = archive_path
    folder.archived_at = archived_at
    folder.archived_by_user_id = user.id
    session.commit()
