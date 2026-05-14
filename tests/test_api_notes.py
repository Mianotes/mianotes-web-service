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


def test_create_note_from_text_writes_files_and_db_records(client: TestClient, tmp_path: Path):
    user = client.post(
        "/api/users",
        json={"email": "note@example.com", "name": "Note User"},
    ).json()
    topic = client.post(
        "/api/topics",
        json={"user_id": user["id"], "name": "Meeting Notes"},
    ).json()

    response = client.post(
        "/api/notes/from-text",
        json={
            "user_id": user["id"],
            "topic_id": topic["id"],
            "title": "Kickoff Notes",
            "text": "We agreed to build Mianotes with Markdown notes.",
        },
    )

    assert response.status_code == 201
    note = response.json()
    assert note["id"]
    assert note["title"] == "Kickoff Notes"
    assert note["user"]["id"] == user["id"]
    assert note["topic"]["id"] == topic["id"]
    assert "# Kickoff Notes" in note["text"]
    assert "We agreed to build Mianotes" in note["text"]
    assert note["note_url"].endswith("/data/926c16eeec762774/meeting-notes/kickoff-notes.md")
    assert note["source_files"][0]["url"].endswith(
        "/data/926c16eeec762774/meeting-notes/kickoff-notes.source.txt"
    )
    assert note["comments_url"].endswith(
        "/data/926c16eeec762774/meeting-notes/kickoff-notes.comments.json"
    )

    note_path = tmp_path / "data" / "926c16eeec762774" / "meeting-notes" / "kickoff-notes.md"
    source_path = (
        tmp_path / "data" / "926c16eeec762774" / "meeting-notes" / "kickoff-notes.source.txt"
    )
    comments_path = (
        tmp_path / "data" / "926c16eeec762774" / "meeting-notes" / "kickoff-notes.comments.json"
    )
    assert note_path.read_text(encoding="utf-8").startswith("# Kickoff Notes")
    assert (
        source_path.read_text(encoding="utf-8")
        == "We agreed to build Mianotes with Markdown notes."
    )
    assert comments_path.read_text(encoding="utf-8") == '{\n  "comments": []\n}\n'

    listed = client.get("/api/notes", params={"user_id": user["id"]})
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == note["id"]


def test_create_note_from_text_accepts_plain_notes_endpoint(client: TestClient):
    user = client.post(
        "/api/users",
        json={"email": "plain@example.com", "name": "Plain User"},
    ).json()
    topic = client.post(
        "/api/topics",
        json={"user_id": user["id"], "name": "Inbox"},
    ).json()

    response = client.post(
        "/api/notes",
        json={
            "user_id": user["id"],
            "topic_id": topic["id"],
            "text": "This note has no provided title, so the API infers one.",
        },
    )

    assert response.status_code == 201
    assert response.json()["title"] == "This note has no provided title, so the API infers one"
