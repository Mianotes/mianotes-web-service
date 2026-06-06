import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db.models import Base, Folder, User, new_id
from mianotes_web_service.services.folder_repository import (
    FolderRepository,
    ensure_can_change_folder,
    ensure_folder_active,
)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _user(session, *, is_admin: bool = False) -> User:
    user = User(
        id=new_id(),
        email=f"{new_id()}@example.com",
        name="Folder User",
        username=f"user-{new_id()[:8]}",
        is_admin=is_admin,
    )
    session.add(user)
    session.commit()
    return user


def _folder(session, user: User, *, name: str = "Docs", slug: str = "docs") -> Folder:
    folder = Folder(
        id=new_id(),
        user_id=user.id,
        name=name,
        slug=slug,
        path=slug,
    )
    session.add(folder)
    session.commit()
    return folder


def test_folder_repository_unique_slug_appends_folder_id_when_needed():
    session = _session()
    owner = _user(session)
    existing = _folder(session, owner, name="Docs", slug="docs")
    renamed = _folder(session, owner, name="Docs Draft", slug="docs-draft")

    slug = FolderRepository(session).unique_slug("docs", renamed.id)

    assert slug == f"docs-{renamed.id.replace('-', '')[:8]}"
    assert FolderRepository(session).unique_slug("docs", existing.id) == "docs"


def test_folder_repository_permission_guards():
    session = _session()
    owner = _user(session)
    other_user = _user(session)
    admin = _user(session, is_admin=True)
    folder = _folder(session, owner)

    ensure_can_change_folder(folder, owner)
    ensure_can_change_folder(folder, admin)
    with pytest.raises(HTTPException) as denied:
        ensure_can_change_folder(folder, other_user)
    assert denied.value.status_code == 403

    ensure_folder_active(folder)
    folder.archived_at = folder.created_at
    with pytest.raises(HTTPException) as archived:
        ensure_folder_active(folder)
    assert archived.value.status_code == 404
