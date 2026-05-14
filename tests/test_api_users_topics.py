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
    assert len(user["username"]) == 16

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


def test_topic_crud_and_user_filter(client: TestClient):
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
        "/api/topics",
        json={"user_id": "missing", "name": "Product Research"},
    )
    assert unauthenticated.status_code == 401

    created = client.post(
        "/api/topics",
        json={"name": "Product Research"},
    )
    assert created.status_code == 201
    topic = created.json()
    assert topic["slug"] == "product-research"

    duplicate = client.post(
        "/api/topics",
        json={"user_id": user["id"], "name": "Product Research"},
    )
    assert duplicate.status_code == 409

    listed = client.get("/api/topics", params={"user_id": user["id"]})
    assert listed.status_code == 200
    assert topic["id"] in [item["id"] for item in listed.json()]

    deleted = client.delete(f"/api/topics/{topic['id']}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/topics/{topic['id']}")
    assert missing.status_code == 200
    assert missing.json()["archived_at"] is not None

    visible = client.get("/api/topics", params={"user_id": user["id"]})
    assert visible.status_code == 200
    assert topic["id"] not in [item["id"] for item in visible.json()]
