from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
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
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )

    response = client.post("/api/users", json={"email": "ALICE@example.com", "name": "Alice"})
    assert response.status_code == 201
    user = response.json()
    assert user["email"] == "alice@example.com"
    assert user["name"] == "Alice"
    assert user["username"].startswith("alice-")

    duplicate = client.post("/api/users", json={"email": "alice@example.com", "name": "Alice Two"})
    assert duplicate.status_code == 409

    updated = client.patch(f"/api/users/{user['id']}", json={"name": "Alice Morgan"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Alice Morgan"

    listed = client.get("/api/users")
    assert listed.status_code == 200
    assert user["id"] in [item["id"] for item in listed.json()]

    deleted = client.delete(f"/api/users/{user['id']}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/users/{user['id']}")
    assert missing.status_code == 404


def test_project_crud_and_user_filter(client: TestClient, tmp_path: Path):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "ben@example.com",
            "name": "Ben",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]

    unauthenticated = TestClient(client.app).post(
        "/api/projects",
        json={"user_id": "missing", "name": "Product Research"},
    )
    assert unauthenticated.status_code == 401

    created = client.post(
        "/api/projects",
        json={"name": "Product Research", "is_pinned": True},
    )
    assert created.status_code == 201
    project = created.json()
    assert project["slug"] == "product-research"
    assert project["path"] == "product-research"
    assert project["is_pinned"] is True
    project_dir = tmp_path / "data" / "product-research"
    project_dir.mkdir(parents=True)
    (project_dir / "note.md").write_text("note", encoding="utf-8")

    duplicate = client.post(
        "/api/projects",
        json={"user_id": user["id"], "name": "Product Research"},
    )
    assert duplicate.status_code == 409

    listed = client.get("/api/projects", params={"user_id": user["id"]})
    assert listed.status_code == 200
    assert project["id"] in [item["id"] for item in listed.json()]

    unpinned = client.post("/api/projects", json={"name": "Later Project"}).json()
    ordered = client.get("/api/projects", params={"user_id": user["id"]}).json()
    assert ordered[0]["id"] == project["id"]
    assert ordered[1]["id"] == unpinned["id"]

    updated = client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "Research Notes", "is_pinned": False},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Research Notes"
    assert updated.json()["slug"] == "research-notes"
    assert updated.json()["path"] == "research-notes"
    assert updated.json()["is_pinned"] is False
    assert not project_dir.exists()
    assert (tmp_path / "data" / "research-notes" / "note.md").read_text(
        encoding="utf-8"
    ) == "note"

    deleted = client.delete(f"/api/projects/{project['id']}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/projects/{project['id']}")
    assert missing.status_code == 200
    assert missing.json()["archived_at"] is not None

    visible = client.get("/api/projects", params={"user_id": user["id"]})
    assert visible.status_code == 200
    assert project["id"] not in [item["id"] for item in visible.json()]
