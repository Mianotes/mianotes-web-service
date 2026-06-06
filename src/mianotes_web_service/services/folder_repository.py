from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Folder, PublishedSite, User
from mianotes_web_service.services.storage import short_id


class FolderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def read_or_404(self, folder_id: str) -> Folder:
        folder = self.session.get(Folder, folder_id)
        if folder is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        return folder

    def list_ordered(
        self,
        *,
        user_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Folder]:
        statement = folder_order_statement()
        if user_id is not None:
            statement = statement.where(Folder.user_id == user_id)
        if not include_archived:
            statement = statement.where(Folder.archived_at.is_(None))
        return list(self.session.scalars(statement))

    def ordered_active(self) -> list[Folder]:
        return list(self.session.scalars(folder_order_statement().where(Folder.archived_at.is_(None))))

    def by_ids(self, folder_ids: list[str]) -> dict[str, Folder]:
        folders = list(self.session.scalars(select(Folder).where(Folder.id.in_(folder_ids))))
        return {folder.id: folder for folder in folders}

    def next_sort_order(self, user_id: str) -> int:
        current = self.session.scalar(
            select(func.max(Folder.sort_order)).where(
                Folder.user_id == user_id,
                Folder.archived_at.is_(None),
            )
        )
        return (current or 0) + 10

    def slug_exists(self, slug: str, folder_id: str | None = None) -> bool:
        statement = select(Folder).where(Folder.slug == slug)
        if folder_id is not None:
            statement = statement.where(Folder.id != folder_id)
        return self.session.scalars(statement).first() is not None

    def unique_slug(self, slug: str, folder_id: str) -> str:
        if not self.slug_exists(slug, folder_id):
            return slug

        base_candidate = f"{slug}-{short_id(folder_id)}"
        if not self.slug_exists(base_candidate, folder_id):
            return base_candidate

        index = 2
        candidate = f"{base_candidate}-{index}"
        while self.slug_exists(candidate, folder_id):
            index += 1
            candidate = f"{base_candidate}-{index}"
        return candidate

    def slug_conflict(self, slug: str, folder_id: str) -> Folder | None:
        return self.session.scalars(
            select(Folder).where(Folder.slug == slug, Folder.id != folder_id)
        ).one_or_none()

    def remove_stale_archived_folder(self, folder: Folder) -> None:
        for site in self.session.scalars(
            select(PublishedSite).where(PublishedSite.folder_id == folder.id)
        ):
            site.folder_id = None
        self.session.delete(folder)
        self.session.commit()


def folder_order_statement() -> Select[tuple[Folder]]:
    return select(Folder).order_by(
        Folder.is_pinned.desc(),
        Folder.sort_order.asc(),
        Folder.created_at.desc(),
    )


def ensure_can_change_folder(
    folder: Folder,
    user: User,
    *,
    detail: str = "Only the folder owner or an admin can change this folder",
) -> None:
    if not user.is_admin and folder.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


def ensure_folder_active(folder: Folder) -> None:
    if folder.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
