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


def _join_admin(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    assert response.status_code == 201
    return response.json()["user"]


def test_api_token_auth_scope_and_revocation(client: TestClient):
    _join_admin(client)
    project = client.post("/api/projects", json={"name": "Agents"}).json()

    created = client.post(
        "/api/tokens",
        json={
            "name": "Read only agent",
            "scopes": ["notes:read", "projects:read", "tokens:read"],
        },
    )
    assert created.status_code == 201
    created_body = created.json()
    raw_token = created_body["token"]
    assert raw_token.startswith("mia_")
    assert created_body["token_prefix"] == raw_token[:12]

    listed = client.get("/api/tokens")
    assert listed.status_code == 200
    assert "token" not in listed.json()[0]

    agent_client = TestClient(client.app)
    headers = {"Authorization": f"Bearer {raw_token}"}

    projects = agent_client.get("/api/projects", headers=headers)
    assert projects.status_code == 200

    denied_write = agent_client.post("/api/projects", json={"name": "Denied"}, headers=headers)
    assert denied_write.status_code == 403

    notes = agent_client.get("/api/notes", headers=headers)
    assert notes.status_code == 200

    created_note = agent_client.post(
        "/api/notes/from-text",
        json={"project_id": project["id"], "text": "Token should not write notes."},
        headers=headers,
    )
    assert created_note.status_code == 403

    revoked = client.delete(f"/api/tokens/{created_body['id']}")
    assert revoked.status_code == 204

    after_revoke = agent_client.get("/api/projects", headers=headers)
    assert after_revoke.status_code == 401


def test_admin_token_can_use_admin_endpoints(client: TestClient):
    _join_admin(client)
    created = client.post(
        "/api/tokens",
        json={"name": "Admin agent", "scopes": ["admin"]},
    )
    assert created.status_code == 201
    raw_token = created.json()["token"]

    agent_client = TestClient(client.app)
    created_user = agent_client.post(
        "/api/users",
        json={"email": "agent-created@example.com", "name": "Agent Created"},
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert created_user.status_code == 201


def test_rejects_invalid_token_scope(client: TestClient):
    _join_admin(client)
    rejected = client.post(
        "/api/tokens",
        json={"name": "Bad token", "scopes": ["notes:explode"]},
    )
    assert rejected.status_code == 422
