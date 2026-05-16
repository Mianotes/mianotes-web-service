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
    assert note["source_type"] == "text"
    assert note["revision_number"] == 1
    assert note["is_published"] is False
    assert "# Kickoff Notes" in note["text"]
    assert "We agreed to build Mianotes" in note["text"]
    assert note["note_url"].endswith(f"/data/926c16eeec762774/meeting-notes/{note['id']}.md")
    assert note["source_files"][0]["url"].endswith(
        f"/data/926c16eeec762774/meeting-notes/{note['id']}.source.txt"
    )
    assert note["comments_count"] == 0
    assert note["comments_url"].endswith(f"/api/notes/{note['id']}/comments")

    note_path = tmp_path / "data" / "926c16eeec762774" / "meeting-notes" / f"{note['id']}.md"
    source_path = (
        tmp_path
        / "data"
        / "926c16eeec762774"
        / "meeting-notes"
        / f"{note['id']}.source.txt"
    )
    assert note_path.read_text(encoding="utf-8").startswith("# Kickoff Notes")
    assert (
        source_path.read_text(encoding="utf-8")
        == "We agreed to build Mianotes with Markdown notes."
    )
    assert not (
        tmp_path
        / "data"
        / "926c16eeec762774"
        / "meeting-notes"
        / f"{note['id']}.comments.json"
    ).exists()

    listed = client.get("/api/notes", params={"topic_id": topic["id"]})
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == note["id"]
    assert listed.json()[0]["status"] == "ready"
    assert listed.json()[0]["source_type"] == "text"


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
    assert note["note_id"] == note["id"]
    assert note["source_type"] == "pdf"
    assert note["job_id"] == note["job"]["id"]
    assert note["job_status"] == "queued"
    assert note["job"]["job_type"] == "parse_file"
    assert note["job"]["status"] == "queued"
    assert note["job"]["note_id"] == note["id"]
    assert note["note_api_url"].endswith(f"/api/notes/{note['id']}")
    assert note["job_api_url"].endswith(f"/api/jobs/{note['job']['id']}")
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


def test_create_note_from_url_queues_parse_job(client: TestClient, tmp_path: Path):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "url@example.com",
            "name": "URL User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    topic = client.post("/api/topics", json={"name": "Links"}).json()

    response = client.post(
        "/api/notes/from-url",
        json={
            "topic_id": topic["id"],
            "url": "https://example.com/articles/mianotes",
            "tags": ["research"],
        },
    )

    assert response.status_code == 201
    note = response.json()
    assert note["user"]["id"] == user["id"]
    assert note["topic"]["id"] == topic["id"]
    assert note["title"] == "mianotes"
    assert note["status"] == "pending_parse"
    assert note["note_id"] == note["id"]
    assert note["source_type"] == "link"
    assert note["job_id"] == note["job"]["id"]
    assert note["job_status"] == "queued"
    assert note["job"]["job_type"] == "parse_url"
    assert note["job"]["status"] == "queued"
    assert note["job"]["input"]["url"] == "https://example.com/articles/mianotes"
    assert note["note_api_url"].endswith(f"/api/notes/{note['id']}")
    assert note["job_api_url"].endswith(f"/api/jobs/{note['job']['id']}")
    assert [tag["slug"] for tag in note["tags"]] == ["research"]
    assert "waiting for the parsing pipeline" in note["text"]

    note_path = tmp_path / "data" / "09592df946423e42" / "links" / f"{note['id']}.md"
    source_path = (
        tmp_path / "data" / "09592df946423e42" / "links" / f"{note['id']}.source.html"
    )
    assert note_path.read_text(encoding="utf-8").startswith("# mianotes")
    assert note["source_files"][0]["original_filename"] == "https://example.com/articles/mianotes"
    assert note["source_files"][0]["url"].endswith(
        f"/data/09592df946423e42/links/{note['id']}.source.html"
    )
    assert not source_path.exists()


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


def test_note_tags_comments_and_share_link(client: TestClient):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "share@example.com",
            "name": "Share User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    topic = client.post("/api/topics", json={"name": "Collaboration"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "topic_id": topic["id"],
            "title": "Shared Research",
            "text": "Useful research note.",
            "tags": ["Research", "summer-2026"],
        },
    ).json()

    assert {tag["slug"] for tag in note["tags"]} == {"research", "summer-2026"}
    listed_tags = client.get("/api/tags")
    assert listed_tags.status_code == 200
    assert {tag["slug"] for tag in listed_tags.json()} == {"research", "summer-2026"}

    updated = client.put(
        f"/api/notes/{note['id']}/tags",
        json={"tags": ["research-edge-ai"]},
    )
    assert updated.status_code == 200
    assert [tag["slug"] for tag in updated.json()["tags"]] == ["research-edge-ai"]

    too_many_tags = ["one", "two", "three", "four", "five", "six"]
    rejected_update = client.put(
        f"/api/notes/{note['id']}/tags",
        json={"tags": too_many_tags},
    )
    assert rejected_update.status_code == 422

    rejected_create = client.post(
        "/api/notes/from-text",
        json={
            "topic_id": topic["id"],
            "title": "Too many tags",
            "text": "This note should not be created.",
            "tags": too_many_tags,
        },
    )
    assert rejected_create.status_code == 422

    comment = client.post(
        f"/api/notes/{note['id']}/comments",
        json={"body": "This is useful for the next call."},
    )
    assert comment.status_code == 201
    comment_body = comment.json()
    assert comment_body["body"] == "This is useful for the next call."
    assert comment_body["user"]["id"] == user["id"]

    comments = client.get(f"/api/notes/{note['id']}/comments")
    assert comments.status_code == 200
    assert [item["body"] for item in comments.json()] == ["This is useful for the next call."]

    shared = client.post(f"/api/notes/{note['id']}/share")
    assert shared.status_code == 200
    share_url = shared.json()["share_url"]
    assert "/api/notes/shared/" in share_url

    guest_note = TestClient(client.app).get(share_url.removeprefix("http://testserver"))
    assert guest_note.status_code == 200
    assert guest_note.json()["id"] == note["id"]
    assert guest_note.json()["share_url"] == share_url

    disabled = client.delete(f"/api/notes/{note['id']}/share")
    assert disabled.status_code == 204
    guest_missing = TestClient(client.app).get(share_url.removeprefix("http://testserver"))
    assert guest_missing.status_code == 404
