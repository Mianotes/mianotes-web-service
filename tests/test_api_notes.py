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
        "/api/auth/join",
        json={
            "email": "note@example.com",
            "name": "Note User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    topic = client.post(
        "/api/topics",
        json={"name": "Meeting Notes"},
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
    assert note["status"] == "ready"
    assert "# Kickoff Notes" in note["text"]
    assert "We agreed to build Mianotes" in note["text"]
    assert note["note_url"].endswith(f"/data/926c16eeec762774/meeting-notes/{note['id']}.md")
    assert note["source_files"][0]["url"].endswith(
        f"/data/926c16eeec762774/meeting-notes/{note['id']}.source.txt"
    )
    assert note["comments_url"].endswith(
        f"/data/926c16eeec762774/meeting-notes/{note['id']}.comments.json"
    )

    note_path = tmp_path / "data" / "926c16eeec762774" / "meeting-notes" / f"{note['id']}.md"
    source_path = (
        tmp_path
        / "data"
        / "926c16eeec762774"
        / "meeting-notes"
        / f"{note['id']}.source.txt"
    )
    comments_path = (
        tmp_path
        / "data"
        / "926c16eeec762774"
        / "meeting-notes"
        / f"{note['id']}.comments.json"
    )
    assert note_path.read_text(encoding="utf-8").startswith("# Kickoff Notes")
    assert (
        source_path.read_text(encoding="utf-8")
        == "We agreed to build Mianotes with Markdown notes."
    )
    assert comments_path.read_text(encoding="utf-8") == '{\n  "comments": []\n}\n'

    listed = client.get("/api/notes", params={"topic_id": topic["id"]})
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == note["id"]
    assert listed.json()[0]["status"] == "ready"


def test_create_note_from_text_accepts_plain_notes_endpoint(client: TestClient):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "plain@example.com",
            "name": "Plain User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    topic = client.post(
        "/api/topics",
        json={"name": "Inbox"},
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


def test_create_note_from_file_stores_source_and_pending_note(
    client: TestClient,
    tmp_path: Path,
):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "upload@example.com",
            "name": "Upload User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    topic = client.post("/api/topics", json={"name": "Uploads"}).json()

    response = client.post(
        "/api/notes/from-file",
        data={"topic_id": topic["id"], "title": "Receipt"},
        files={"file": ("receipt.pdf", b"%PDF-1.4 test content", "application/pdf")},
    )

    assert response.status_code == 201
    note = response.json()
    assert note["user"]["id"] == user["id"]
    assert note["topic"]["id"] == topic["id"]
    assert note["title"] == "Receipt"
    assert note["status"] == "pending_parse"
    assert "waiting for the parsing pipeline" in note["text"]
    assert note["note_url"].endswith(f"/data/43916aabf99c29b8/uploads/{note['id']}.md")
    assert note["source_files"][0]["original_filename"] == "receipt.pdf"
    assert note["source_files"][0]["url"].endswith(
        f"/data/43916aabf99c29b8/uploads/{note['id']}.source.pdf"
    )

    note_path = tmp_path / "data" / "43916aabf99c29b8" / "uploads" / f"{note['id']}.md"
    source_path = (
        tmp_path / "data" / "43916aabf99c29b8" / "uploads" / f"{note['id']}.source.pdf"
    )
    assert note_path.read_text(encoding="utf-8").startswith("# Receipt")
    assert source_path.read_bytes() == b"%PDF-1.4 test content"


def test_note_changes_are_limited_to_owner_or_admin(client: TestClient):
    admin = client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    topic = client.post("/api/topics", json={"name": "Family"}).json()
    admin_note = client.post(
        "/api/notes/from-text",
        json={
            "topic_id": topic["id"],
            "title": "Admin Note",
            "text": "Only the admin owns this note.",
        },
    ).json()

    maria = client.post(
        "/api/auth/join",
        json={
            "email": "maria@example.com",
            "name": "Maria",
            "password": "house-password",
        },
    ).json()["user"]
    forbidden_update = client.patch(
        f"/api/notes/{admin_note['id']}",
        json={"title": "Maria Edit"},
    )
    assert forbidden_update.status_code == 403

    maria_note = client.post(
        "/api/notes/from-text",
        json={
            "topic_id": topic["id"],
            "title": "Maria Note",
            "text": "Maria can add a note to a shared topic.",
        },
    )
    assert maria_note.status_code == 201
    maria_note_body = maria_note.json()
    assert maria_note_body["user"]["id"] == maria["id"]

    client.post(
        "/api/auth/login",
        json={"user_id": admin["id"], "password": "house-password"},
    )
    admin_update = client.patch(
        f"/api/notes/{maria_note_body['id']}",
        json={"title": "Admin Updated Maria Note", "text": "Admin can help tidy this up."},
    )
    assert admin_update.status_code == 200
    assert admin_update.json()["title"] == "Admin Updated Maria Note"
    assert "Admin can help tidy this up." in admin_update.json()["text"]

    deleted = client.delete(f"/api/notes/{maria_note_body['id']}")
    assert deleted.status_code == 204
    missing = client.get(f"/api/notes/{maria_note_body['id']}")
    assert missing.status_code == 404
