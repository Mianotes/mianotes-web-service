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
from mianotes_web_service.services.search import search_markdown_files


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


def _join_admin(client: TestClient) -> None:
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


def _folder_by_name(client: TestClient, name: str) -> dict:
    folders = client.get("/api/folders").json()
    return next(folder for folder in folders if folder["name"] == name)


def test_search_notes_from_markdown_and_api_token(client: TestClient):
    _join_admin(client)
    folder = client.post("/api/folders", json={"name": "Research"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Mars rover",
            "text": "The Mars rover found structured field notes for future agents.",
        },
    ).json()

    searched = client.get("/api/search", params={"q": "structured field"})
    assert searched.status_code == 200
    results = searched.json()
    assert len(results) == 1
    assert results[0]["note"]["id"] == note["id"]
    assert "structured field notes" in results[0]["excerpt"]

    token = client.post(
        "/api/tokens",
        json={"name": "Search agent", "scopes": ["notes:read"]},
    ).json()["token"]
    agent_client = TestClient(client.app)
    token_search = agent_client.get(
        "/api/search",
        params={"q": "Mars rover"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert token_search.status_code == 200
    assert token_search.json()[0]["note"]["id"] == note["id"]


def test_context_returns_full_note_text_from_folder_and_title(client: TestClient):
    _join_admin(client)
    mianotes = _folder_by_name(client, "Mianotes")
    other = client.post("/api/folders", json={"name": "Work"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": mianotes["id"],
            "title": "Settings Page",
            "text": "Settings page context for profile, model, and local folder controls.",
        },
    ).json()
    client.post(
        "/api/notes/from-text",
        json={
            "folder_id": other["id"],
            "title": "Settings Page",
            "text": "This note should not be returned because it belongs to Work.",
        },
    )

    response = client.get(
        "/api/context",
        params={"folder": "Mianotes", "title": "Settings Page", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["folder"] == "Mianotes"
    assert payload["title"] == "Settings Page"
    assert payload["total"] == 1
    assert payload["results"][0]["note"]["id"] == note["id"]
    assert payload["results"][0]["matched_by"] == "title"
    assert "Settings page context" in payload["results"][0]["text"]


def test_context_works_with_api_token_and_search_fallback(client: TestClient):
    _join_admin(client)
    folder = _folder_by_name(client, "Mianotes")
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Profile screen",
            "text": "The settings page should include profile controls and model preferences.",
        },
    ).json()
    token = client.post(
        "/api/tokens",
        json={"name": "Context agent", "scopes": ["notes:read"]},
    ).json()["token"]
    agent_client = TestClient(client.app)

    response = agent_client.get(
        "/api/context",
        params={"folder": "Mianotes", "title": "settings page", "limit": 5},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["results"][0]["note"]["id"] == note["id"]
    assert payload["results"][0]["matched_by"] == "search"
    assert "profile controls" in payload["results"][0]["text"]


def test_search_service_ignores_non_markdown_files(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "note.md").write_text("hello search target", encoding="utf-8")
    (data_dir / "source.txt").write_text("hello search target", encoding="utf-8")

    matches = search_markdown_files(data_dir, "search target")
    assert [match.path.name for match in matches] == ["note.md"]
