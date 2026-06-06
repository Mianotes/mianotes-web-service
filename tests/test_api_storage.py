import sqlite3
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
from mianotes_web_service.services.storage_settings import workspace_database_path
from mianotes_web_service.services.workspace_markdown_import import (
    COMPATIBLE_MARKDOWN_IMPORT_MESSAGE,
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
    app.state.testing_session_factory = testing_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_storage_capacity_is_authenticated_and_cached(client: TestClient):
    unauthenticated = client.get("/api/storage")
    assert unauthenticated.status_code == 401

    client.post(
        "/api/auth/join",
        json={
            "email": "storage@example.com",
            "name": "Storage User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )

    first = client.get("/api/storage")
    assert first.status_code == 200
    payload = first.json()
    assert payload["data_dir"]
    assert payload["total_bytes"] > 0
    assert payload["free_bytes"] >= 0
    assert payload["used_bytes"] >= 0
    assert payload["data_size_bytes"] >= 0
    assert payload["cache_seconds"] == 3600
    assert payload["refreshed_at"]
    assert payload["cache_expires_at"]

    second = client.get("/api/storage")
    assert second.status_code == 200
    assert second.json()["refreshed_at"] == payload["refreshed_at"]


def test_create_workspace_prompts_before_importing_existing_markdown(
    client: TestClient,
    tmp_path: Path,
):
    _create_admin(client)
    workspace_path = tmp_path / "docs"
    note_path = workspace_path / "markdown" / "about" / "what-is-mianotes-c08cbf08.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("# What is Mianotes?\n\nA local-first knowledge base.", encoding="utf-8")

    response = client.post(
        "/api/settings/storage/locations",
        json={"name": "Docs", "folder_path": str(workspace_path)},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == COMPATIBLE_MARKDOWN_IMPORT_MESSAGE
    assert not (workspace_path / ".mianotes").exists()


def test_create_workspace_can_import_existing_markdown_notes(
    client: TestClient,
    tmp_path: Path,
):
    _create_admin(client)
    workspace_path = tmp_path / "docs"
    note_path = workspace_path / "markdown" / "api-reference" / "api-overview-2bb39d4a.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("# API overview\n\nUseful API docs.", encoding="utf-8")

    response = client.post(
        "/api/settings/storage/locations",
        json={
            "name": "Docs",
            "folder_path": str(workspace_path),
            "import_existing_markdown": True,
        },
    )

    assert response.status_code == 200
    database_path = workspace_database_path(tmp_path / "data", "docs")
    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        folder = connection.execute("SELECT name, slug, path FROM folders").fetchone()
        note = connection.execute("SELECT title, filename, note_path FROM notes").fetchone()
    assert folder == ("API Reference", "api-reference", "api-reference")
    assert note == ("API overview", "api-overview-2bb39d4a.md", str(note_path))
    assert note_path.read_text(encoding="utf-8") == "# API overview\n\nUseful API docs."


def test_create_workspace_can_ignore_existing_markdown_notes(
    client: TestClient,
    tmp_path: Path,
):
    _create_admin(client)
    workspace_path = tmp_path / "docs"
    note_path = workspace_path / "markdown" / "about" / "what-is-mianotes-c08cbf08.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("# What is Mianotes?\n\nA local-first knowledge base.", encoding="utf-8")

    response = client.post(
        "/api/settings/storage/locations",
        json={
            "name": "Docs",
            "folder_path": str(workspace_path),
            "import_existing_markdown": False,
        },
    )

    assert response.status_code == 200
    database_path = workspace_database_path(tmp_path / "data", "docs")
    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM folders").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    assert note_path.exists()


def _create_admin(client: TestClient) -> None:
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
