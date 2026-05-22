from collections.abc import Generator
from io import BytesIO
from pathlib import Path

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
        json={"email": "member@example.com", "name": "Member", "password": "instance-password"},
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
    assert not avatar_path.exists()
    assert (tmp_path / "data" / second_payload["photo_url"].removeprefix("/")).is_file()


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
    folder_dir = tmp_path / "data" / "product-research"
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
    assert ordered[1]["id"] == unpinned["id"]

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
    assert (tmp_path / "data" / "research-notes" / "note.md").read_text(
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
    assert not (tmp_path / "data" / "research-notes").exists()
    archived_note_path = tmp_path / "data" / archived_folder["path"] / "note.md"
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
    restored_note_path = tmp_path / "data" / restored_folder["path"] / "note.md"
    assert restored_note_path.read_text(encoding="utf-8") == "note"

    restored_visible = client.get("/api/folders", params={"user_id": user["id"]})
    assert restored_visible.status_code == 200
    assert folder["id"] in [item["id"] for item in restored_visible.json()]
