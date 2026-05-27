import json
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import AppSetting, Base
from mianotes_web_service.db.session import get_session
from mianotes_web_service.services.auth import (
    INSTANCE_API_TOKEN_PUBLIC_KEY,
    hash_api_token,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("MIANOTES_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MIANOTES_STORAGE_CONFIG_PATH", str(tmp_path / "storage.json"))
    monkeypatch.setenv("MIANOTES_ENV_FILE", str(tmp_path / "mianotes.env"))
    monkeypatch.setenv("MIANOTES_API_KEY", "")
    monkeypatch.setenv("MIANOTES_API_TOKEN", "")
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


def _read_app_setting(client: TestClient, key: str) -> str | None:
    session_gen = client.app.dependency_overrides[get_session]()
    session = next(session_gen)
    try:
        setting = session.get(AppSetting, key)
        return setting.value if setting is not None else None
    finally:
        session_gen.close()


def test_service_api_token_authenticates_as_database_admin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _join_admin(client)
    raw_token = "service-private-token"
    monkeypatch.setenv("MIANOTES_API_TOKEN", raw_token)
    get_settings.cache_clear()

    response = client.get("/api/users", headers={"Authorization": f"Bearer {raw_token}"})

    assert response.status_code == 200
    stored_public_key = _read_app_setting(client, INSTANCE_API_TOKEN_PUBLIC_KEY)
    assert stored_public_key == hash_api_token(raw_token)
    assert stored_public_key != raw_token


def test_service_api_key_env_alias_authenticates_as_database_admin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _join_admin(client)
    raw_token = "service-private-key"
    monkeypatch.setenv("MIANOTES_API_KEY", raw_token)
    get_settings.cache_clear()

    response = client.get("/api/users", headers={"Authorization": f"Bearer {raw_token}"})

    assert response.status_code == 200
    stored_public_key = _read_app_setting(client, INSTANCE_API_TOKEN_PUBLIC_KEY)
    assert stored_public_key == hash_api_token(raw_token)
    assert stored_public_key != raw_token


def test_admin_can_create_service_api_key_from_settings(client: TestClient):
    _join_admin(client)
    storage_path = get_settings().storage_config_path
    storage_config = json.loads(storage_path.read_text(encoding="utf-8"))
    storage_config["apiKey"] = "mia_old_raw_secret"
    storage_path.write_text(json.dumps(storage_config), encoding="utf-8")

    created = client.post("/api/settings/api-key", json={})

    assert created.status_code == 201
    raw_token = created.json()["token"]
    assert created.json()["api_url"] == "http://127.0.0.1:8200"
    assert raw_token.startswith("mia_")
    assert _read_app_setting(client, INSTANCE_API_TOKEN_PUBLIC_KEY) == hash_api_token(raw_token)

    storage_config = json.loads(storage_path.read_text(encoding="utf-8"))
    assert "apiKey" not in storage_config
    assert "apiToken" not in storage_config

    env_file = Path(os.environ["MIANOTES_ENV_FILE"])
    env_contents = env_file.read_text(encoding="utf-8")
    assert 'MIANOTES_API_URL="http://127.0.0.1:8200"' in env_contents
    assert f'MIANOTES_API_KEY="{raw_token}"' in env_contents

    get_settings.cache_clear()
    agent_client = TestClient(client.app)
    response = agent_client.get("/api/users", headers={"Authorization": f"Bearer {raw_token}"})

    assert response.status_code == 200


def test_admin_api_key_creation_preserves_custom_api_url(client: TestClient):
    _join_admin(client)
    env_file = Path(os.environ["MIANOTES_ENV_FILE"])
    env_file.write_text('MIANOTES_API_URL="http://192.168.1.10:8200"\n', encoding="utf-8")

    created = client.post("/api/settings/api-key", json={})

    assert created.status_code == 201
    assert created.json()["api_url"] == "http://192.168.1.10:8200"
    assert 'MIANOTES_API_URL="http://192.168.1.10:8200"' in env_file.read_text(encoding="utf-8")


def test_admin_api_key_creation_normalizes_localhost_api_url(client: TestClient):
    _join_admin(client)
    env_file = Path(os.environ["MIANOTES_ENV_FILE"])
    env_file.write_text('MIANOTES_API_URL="http://localhost:8200"\n', encoding="utf-8")

    created = client.post("/api/settings/api-key", json={})

    assert created.status_code == 201
    assert created.json()["api_url"] == "http://127.0.0.1:8200"
    env_contents = env_file.read_text(encoding="utf-8")
    assert 'MIANOTES_API_URL="http://127.0.0.1:8200"' in env_contents
    assert "localhost:8200" not in env_contents


def test_admin_can_update_workspace_share_address(client: TestClient):
    _join_admin(client)

    initial = client.get("/api/settings/share")
    assert initial.status_code == 200
    assert initial.json() == {"workspace_url": None}

    updated = client.patch(
        "/api/settings/share",
        json={"workspace_url": " https://notes.example.com/ "},
    )

    assert updated.status_code == 200
    assert updated.json() == {"workspace_url": "https://notes.example.com"}
    assert client.get("/api/settings/share").json() == {"workspace_url": "https://notes.example.com"}

    invalid = client.patch("/api/settings/share", json={"workspace_url": "notes.example.com"})
    assert invalid.status_code == 400
    assert "full workspace address" in invalid.json()["detail"]


def test_service_api_token_requires_initialized_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    raw_token = "service-private-token"
    monkeypatch.setenv("MIANOTES_API_TOKEN", raw_token)
    get_settings.cache_clear()

    response = client.get("/api/users", headers={"Authorization": f"Bearer {raw_token}"})

    assert response.status_code == 403
    assert "no admin user yet" in response.json()["detail"]
    assert _read_app_setting(client, INSTANCE_API_TOKEN_PUBLIC_KEY) == hash_api_token(raw_token)


def test_service_api_token_rejects_wrong_bearer_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _join_admin(client)
    monkeypatch.setenv("MIANOTES_API_TOKEN", "service-private-token")
    get_settings.cache_clear()

    response = client.get("/api/users", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API token"


def test_api_token_auth_scope_and_revocation(client: TestClient):
    _join_admin(client)
    folder = client.post("/api/folders", json={"name": "Agents"}).json()

    created = client.post(
        "/api/tokens",
        json={
            "name": "Read only agent",
            "scopes": ["notes:read", "folders:read", "tokens:read"],
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

    folders = agent_client.get("/api/folders", headers=headers)
    assert folders.status_code == 200

    denied_write = agent_client.post("/api/folders", json={"name": "Denied"}, headers=headers)
    assert denied_write.status_code == 403

    notes = agent_client.get("/api/notes", headers=headers)
    assert notes.status_code == 200

    created_note = agent_client.post(
        "/api/notes/from-text",
        json={"folder_id": folder["id"], "text": "Token should not write notes."},
        headers=headers,
    )
    assert created_note.status_code == 403

    revoked = client.delete(f"/api/tokens/{created_body['id']}")
    assert revoked.status_code == 204

    after_revoke = agent_client.get("/api/folders", headers=headers)
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
