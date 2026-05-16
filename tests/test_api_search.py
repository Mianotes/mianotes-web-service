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


def test_search_notes_from_markdown_and_api_token(client: TestClient):
    _join_admin(client)
    project = client.post("/api/projects", json={"name": "Research"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "project_id": project["id"],
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


def test_search_service_ignores_non_markdown_files(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "note.md").write_text("hello search target", encoding="utf-8")
    (data_dir / "source.txt").write_text("hello search target", encoding="utf-8")

    matches = search_markdown_files(data_dir, "search target")
    assert [match.path.name for match in matches] == ["note.md"]
