from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from shutil import rmtree

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Base
from mianotes_web_service.db.session import get_session
from mianotes_web_service.services.storage_settings import (
    DEFAULT_DATABASE_FILE,
    StorageConfig,
    StorageLocation,
    write_storage_config,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("MIANOTES_DATA_DIR", str(tmp_path / "data"))
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_session() -> Generator[Session, None, None]:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_user_crud(client: TestClient):
    unauthenticated = TestClient(client.app).get("/api/users")
    assert unauthenticated.status_code == 401

    client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    )

    response = client.post(
        "/api/users",
        json={
            "email": "ALICE@example.com",
            "name": "Alice",
            "phone": "+44 20 0000 0000",
            "role": "Researcher",
        },
    )
    assert response.status_code == 201
    user = response.json()
    assert user["email"] == "alice@example.com"
    assert user["name"] == "Alice"
    assert user["phone"] == "+44 20 0000 0000"
    assert user["role"] == "Researcher"
    assert user["username"].startswith("alice-")

    duplicate = client.post("/api/users", json={"email": "alice@example.com", "name": "Alice Two"})
    assert duplicate.status_code == 409

    updated = client.patch(
        f"/api/users/{user['id']}",
        json={"name": "Alice Morgan", "phone": "+44 20 1111 1111", "role": "Lead researcher"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Alice Morgan"
    assert updated.json()["phone"] == "+44 20 1111 1111"
    assert updated.json()["role"] == "Lead researcher"

    listed = client.get("/api/users")
    assert listed.status_code == 200
    assert user["id"] in [item["id"] for item in listed.json()]

    deleted = client.delete(f"/api/users/{user['id']}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/users/{user['id']}")
    assert missing.status_code == 404


def test_user_can_update_own_profile_but_not_others(client: TestClient):
    admin = client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    ).json()["user"]
    other_user = client.post(
        "/api/users",
        json={"email": "other@example.com", "name": "Other"},
    ).json()

    client.post("/api/auth/logout")
    joined = client.post(
        "/api/auth/join",
        json={
            "email": "member@example.com",
            "name": "Member",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    )
    member = joined.json()["user"]

    own_update = client.patch(
        f"/api/users/{member['id']}",
        json={"name": "Member Updated", "phone": "123", "role": "Writer"},
    )
    assert own_update.status_code == 200
    assert own_update.json()["name"] == "Member Updated"
    assert own_update.json()["phone"] == "123"
    assert own_update.json()["role"] == "Writer"

    forbidden = client.patch(f"/api/users/{other_user['id']}", json={"name": "Nope"})
    assert forbidden.status_code == 403

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"user_id": admin["id"], "password": "instance-password"})
    admin_update = client.patch(f"/api/users/{other_user['id']}", json={"role": "Designer"})
    assert admin_update.status_code == 200
    assert admin_update.json()["role"] == "Designer"


def test_admin_can_manage_user_admin_role(client: TestClient):
    admin = client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    ).json()["user"]
    member = client.post(
        "/api/users",
        json={"email": "member@example.com", "name": "Member"},
    ).json()

    promoted = client.patch(f"/api/users/{member['id']}/admin", json={"is_admin": True})
    assert promoted.status_code == 200
    assert promoted.json()["is_admin"] is True

    demoted = client.patch(f"/api/users/{member['id']}/admin", json={"is_admin": False})
    assert demoted.status_code == 200
    assert demoted.json()["is_admin"] is False

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"user_id": member["id"], "password": "instance-password"})
    forbidden = client.patch(f"/api/users/{admin['id']}/admin", json={"is_admin": False})
    assert forbidden.status_code == 403


def test_admin_can_update_user_password(client: TestClient):
    admin = client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    ).json()["user"]
    member = client.post(
        "/api/users",
        json={"email": "member@example.com", "name": "Member"},
    ).json()

    mismatch = client.patch(
        f"/api/users/{member['id']}/password",
        json={"password": "new-password", "password_confirmation": "different"},
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["detail"] == "Passwords do not match"

    updated = client.patch(
        f"/api/users/{member['id']}/password",
        json={"password": "new-password", "password_confirmation": "new-password"},
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == member["id"]

    client.post("/api/auth/logout")
    logged_in = client.post(
        "/api/auth/login",
        json={"user_id": member["id"], "password": "new-password"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["id"] == member["id"]

    forbidden = client.patch(
        f"/api/users/{admin['id']}/password",
        json={"password": "another-password", "password_confirmation": "another-password"},
    )
    assert forbidden.status_code == 403


def test_workspace_keeps_at_least_one_admin(client: TestClient):
    admin = client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    ).json()["user"]

    demoted = client.patch(f"/api/users/{admin['id']}/admin", json={"is_admin": False})
    assert demoted.status_code == 400
    assert demoted.json()["detail"] == "This workspace needs at least one admin."

    deleted = client.delete(f"/api/users/{admin['id']}")
    assert deleted.status_code == 400
    assert deleted.json()["detail"] == "Admins cannot delete their own account."


def test_user_can_upload_resized_profile_photo(client: TestClient, tmp_path: Path):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    ).json()["user"]

    image_bytes = BytesIO()
    Image.new("RGB", (400, 300), "#1684ff").save(image_bytes, format="PNG")
    image_bytes.seek(0)

    response = client.post(
        f"/api/users/{user['id']}/photo",
        files={"photo": ("avatar.png", image_bytes, "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["photo_url"].startswith(f"/.profiles/{user['id']}/avatar-")
    assert payload["photo_url"].endswith(".jpg")

    avatar_path = tmp_path / "data" / payload["photo_url"].removeprefix("/")
    assert avatar_path.is_file()
    with Image.open(avatar_path) as avatar:
        assert avatar.size == (200, 200)

    second_image_bytes = BytesIO()
    Image.new("RGB", (300, 400), "#fdc13e").save(second_image_bytes, format="PNG")
    second_image_bytes.seek(0)

    second_response = client.post(
        f"/api/users/{user['id']}/photo",
        files={"photo": ("avatar-2.png", second_image_bytes, "image/png")},
    )

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["photo_url"].startswith(f"/.profiles/{user['id']}/avatar-")
    assert second_payload["photo_url"].endswith(".jpg")
    assert second_payload["photo_url"] != payload["photo_url"]
    assert avatar_path.exists()
    assert (tmp_path / "data" / second_payload["photo_url"].removeprefix("/")).is_file()


def test_profile_photo_serves_from_global_data_after_workspace_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_dir = tmp_path / "data"
    blog_dir = tmp_path / "blog"
    config_path = tmp_path / "workspaces.json"
    write_storage_config(
        config_path,
        StorageConfig(
            active_location="default",
            database_file=DEFAULT_DATABASE_FILE,
            locations=[
                StorageLocation(
                    id="default",
                    name="Main workspace",
                    folder_path=data_dir,
                ),
                StorageLocation(
                    id="blog",
                    name="Blog",
                    folder_path=blog_dir,
                ),
            ],
        ),
    )
    monkeypatch.setenv("MIANOTES_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MIANOTES_STORAGE_CONFIG_PATH", str(config_path))
    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as workspace_client:
        user = workspace_client.post(
            "/api/auth/join",
            json={
                "email": "avatar-workspace@example.com",
                "name": "Avatar Workspace User",
                "password": "instance-password",
                "password_confirmation": "instance-password",
            },
        ).json()["user"]

        image_bytes = BytesIO()
        Image.new("RGB", (400, 300), "#1684ff").save(image_bytes, format="PNG")
        image_bytes.seek(0)

        photo_response = workspace_client.post(
            f"/api/users/{user['id']}/photo",
            files={"photo": ("avatar.png", image_bytes, "image/png")},
        )
        assert photo_response.status_code == 200
        photo_url = photo_response.json()["photo_url"]
        assert (data_dir / photo_url.removeprefix("/")).is_file()
        assert not (blog_dir / photo_url.removeprefix("/")).exists()

        switched = workspace_client.patch(
            "/api/settings/storage/active",
            json={"location_id": "blog"},
        )
        assert switched.status_code == 200

        loaded_photo = workspace_client.get(photo_url)
        assert loaded_photo.status_code == 200
        assert loaded_photo.headers["content-type"] == "image/jpeg"

    get_settings.cache_clear()


def test_folder_crud_and_user_filter(client: TestClient, tmp_path: Path):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "ben@example.com",
            "name": "Ben",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    ).json()["user"]

    unauthenticated = TestClient(client.app).post(
        "/api/folders",
        json={"user_id": "missing", "name": "Product Research"},
    )
    assert unauthenticated.status_code == 401

    created = client.post(
        "/api/folders",
        json={"name": "Product Research", "is_pinned": True},
    )
    assert created.status_code == 201
    folder = created.json()
    assert folder["slug"] == "product-research"
    assert folder["path"] == "product-research"
    assert folder["is_pinned"] is True
    assert folder["sort_order"] == 10
    folder_dir = tmp_path / "data" / "markdown" / "product-research"
    folder_dir.mkdir(parents=True)
    (folder_dir / "note.md").write_text("note", encoding="utf-8")

    duplicate = client.post(
        "/api/folders",
        json={"user_id": user["id"], "name": "Product Research"},
    )
    assert duplicate.status_code == 409

    listed = client.get("/api/folders", params={"user_id": user["id"]})
    assert listed.status_code == 200
    assert folder["id"] in [item["id"] for item in listed.json()]

    unpinned = client.post("/api/folders", json={"name": "Later Folder"}).json()
    ordered = client.get("/api/folders", params={"user_id": user["id"]}).json()
    assert ordered[0]["id"] == folder["id"]
    assert unpinned["id"] in [item["id"] for item in ordered]

    updated = client.patch(
        f"/api/folders/{folder['id']}",
        json={"name": "Research Notes", "is_pinned": False},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Research Notes"
    assert updated.json()["slug"] == "research-notes"
    assert updated.json()["path"] == "research-notes"
    assert updated.json()["is_pinned"] is False
    assert not folder_dir.exists()
    assert (tmp_path / "data" / "markdown" / "research-notes" / "note.md").read_text(
        encoding="utf-8"
    ) == "note"

    deleted = client.delete(f"/api/folders/{folder['id']}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/folders/{folder['id']}")
    assert missing.status_code == 200
    archived_folder = missing.json()
    assert archived_folder["archived_at"] is not None
    assert archived_folder["slug"].startswith("research-notes-")
    assert archived_folder["path"].startswith(".archived/research-notes-")
    assert not (tmp_path / "data" / "markdown" / "research-notes").exists()
    archived_note_path = tmp_path / "data" / "markdown" / archived_folder["path"] / "note.md"
    assert archived_note_path.read_text(encoding="utf-8") == "note"

    visible = client.get("/api/folders", params={"user_id": user["id"]})
    assert visible.status_code == 200
    assert folder["id"] not in [item["id"] for item in visible.json()]

    recreated = client.post(
        "/api/folders",
        json={"name": "Research Notes"},
    )
    assert recreated.status_code == 201
    assert recreated.json()["slug"] == "research-notes"

    restored = client.post(f"/api/folders/{folder['id']}/restore", json={})
    assert restored.status_code == 200
    restored_folder = restored.json()
    assert restored_folder["archived_at"] is None
    assert restored_folder["archived_by_user_id"] is None
    assert restored_folder["name"] == "Research Notes"
    assert restored_folder["slug"].startswith("research-notes-")
    assert restored_folder["path"] == restored_folder["slug"]
    assert not archived_note_path.exists()
    restored_note_path = tmp_path / "data" / "markdown" / restored_folder["path"] / "note.md"
    assert restored_note_path.read_text(encoding="utf-8") == "note"

    restored_visible = client.get("/api/folders", params={"user_id": user["id"]})
    assert restored_visible.status_code == 200
    assert folder["id"] in [item["id"] for item in restored_visible.json()]


def test_missing_archived_folder_is_removed_from_restore_list(
    client: TestClient,
    tmp_path: Path,
):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "stale-archive@example.com",
            "name": "Stale Archive User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    folder = client.post("/api/folders", json={"name": "Temporary Docs"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Temporary note",
            "text": "This file was manually removed after archiving.",
        },
    ).json()

    archived = client.delete(f"/api/folders/{folder['id']}")
    assert archived.status_code == 204

    archived_folder = client.get(f"/api/folders/{folder['id']}").json()
    archive_path = tmp_path / "data" / "markdown" / archived_folder["path"]
    assert archive_path.exists()
    rmtree(archive_path)

    restored = client.post(f"/api/folders/{folder['id']}/restore", json={})
    assert restored.status_code == 404
    assert restored.json()["detail"] == "Archived folder no longer exists in the filesystem"

    archived_folders = client.get(
        "/api/folders",
        params={"user_id": user["id"], "include_archived": True},
    )
    assert archived_folders.status_code == 200
    assert folder["id"] not in [item["id"] for item in archived_folders.json()]

    missing_note = client.get(f"/api/notes/{note['id']}")
    assert missing_note.status_code == 404


def test_unpinned_folders_can_be_reordered(client: TestClient):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "ben@example.com",
            "name": "Ben",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    ).json()["user"]
    pinned = client.post("/api/folders", json={"name": "Pinned", "is_pinned": True}).json()
    default_folder = next(
        folder for folder in client.get("/api/folders", params={"user_id": user["id"]}).json()
        if folder["name"] == "Mianotes"
    )
    first = client.post("/api/folders", json={"name": "First"}).json()
    second = client.post("/api/folders", json={"name": "Second"}).json()
    third = client.post("/api/folders", json={"name": "Third"}).json()

    reordered = client.patch(
        "/api/folders/order",
        json={"folder_ids": [third["id"], first["id"], default_folder["id"], second["id"]]},
    )

    assert reordered.status_code == 200
    ordered = client.get("/api/folders", params={"user_id": user["id"]}).json()
    assert [folder["id"] for folder in ordered] == [
        pinned["id"],
        third["id"],
        first["id"],
        default_folder["id"],
        second["id"],
    ]
    assert [folder["sort_order"] for folder in ordered[1:]] == [10, 20, 30, 40]


def test_pinned_folders_must_be_unpinned_before_reordering(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "ben@example.com",
            "name": "Ben",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    )
    pinned = client.post("/api/folders", json={"name": "Pinned", "is_pinned": True}).json()
    folder = client.post("/api/folders", json={"name": "Regular"}).json()

    response = client.patch(
        "/api/folders/order",
        json={"folder_ids": [folder["id"], pinned["id"]]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Pinned folders must be unpinned before sorting"
