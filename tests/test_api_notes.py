from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.api.note_ingestion import _enqueue_job
from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Base, MiaJob, Note, User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.services import job_runner
from mianotes_web_service.services.storage_settings import (
    DEFAULT_DATABASE_FILE,
    StorageConfig,
    StorageLocation,
    write_storage_config,
)
from mianotes_web_service.services.workspace_context import WorkspaceContext


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


def test_enqueue_job_uses_session_workspace(tmp_path: Path):
    calls = []

    class FakeJobRunner:
        def enqueue(self, background_tasks, job_id: str, workspace=None):
            calls.append((background_tasks, job_id, workspace))

    background_tasks = object()
    workspace = WorkspaceContext(
        id="blog",
        name="Blog",
        folder_path=tmp_path / "blog",
        database_file="mia.db",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(job_runner=FakeJobRunner()))
    )
    session = SimpleNamespace(info={"workspace": workspace})

    _enqueue_job(request, background_tasks, "job-id", session)

    assert calls == [(background_tasks, "job-id", workspace)]


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
    folder = client.post(
        "/api/folders",
        json={"name": "Meeting Notes"},
    ).json()

    response = client.post(
        "/api/notes/from-text",
        json={
            "user_id": user["id"],
            "folder_id": folder["id"],
            "title": "Kickoff Notes",
            "text": "We agreed to build Mianotes with Markdown notes.",
        },
    )

    assert response.status_code == 201
    note = response.json()
    assert note["id"]
    assert note["title"] == "Kickoff Notes"
    assert note["user"]["id"] == user["id"]
    assert note["folder"]["id"] == folder["id"]
    assert note["status"] == "ready"
    assert note["source_type"] == "text"
    assert note["revision_number"] == 1
    assert note["is_published"] is False
    assert note["is_starred"] is False
    assert note["summary"] == "We agreed to build Mianotes with Markdown notes."
    assert "# Kickoff Notes" in note["text"]
    assert "We agreed to build Mianotes" in note["text"]
    note_filename = f"kickoff-notes-{note['id'][:8]}"
    assert note["note_url"].endswith(f"/markdown/meeting-notes/{note_filename}.md")
    assert note["source_files"][0]["url"].endswith(
        f"/markdown/meeting-notes/sources/{note['id'][:8]}/original.txt"
    )
    assert note["comments_count"] == 0
    assert note["comments_url"].endswith(f"/api/notes/{note['id']}/comments")

    note_path = tmp_path / "data" / "markdown" / "meeting-notes" / f"{note_filename}.md"
    source_path = (
        tmp_path
        / "data"
        / "markdown"
        / "meeting-notes"
        / "sources"
        / note["id"][:8]
        / "original.txt"
    )
    assert (tmp_path / "data" / "markdown" / "meeting-notes" / ".gitignore").read_text(
        encoding="utf-8"
    ) == "/sources/\n"
    assert note_path.read_text(encoding="utf-8").startswith("# Kickoff Notes")
    assert (
        source_path.read_text(encoding="utf-8")
        == "We agreed to build Mianotes with Markdown notes."
    )
    listed = client.get("/api/notes", params={"folder_id": folder["id"]})
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == note["id"]
    assert listed.json()[0]["status"] == "ready"
    assert listed.json()[0]["source_type"] == "text"
    assert listed.json()[0]["is_starred"] is False
    assert listed.json()[0]["summary"] == "We agreed to build Mianotes with Markdown notes."
    assert listed.json()[0]["filename"] == f"{note_filename}.md"
    assert "text" not in listed.json()[0]

    note_file_response = client.get(f"/markdown/meeting-notes/{note_filename}.md")
    assert note_file_response.status_code == 200
    assert note_file_response.text.startswith("# Kickoff Notes")

    source_file_response = client.get(
        f"/markdown/meeting-notes/sources/{note['id'][:8]}/original.txt"
    )
    assert source_file_response.status_code == 200
    assert source_file_response.text == "We agreed to build Mianotes with Markdown notes."

    public_client = TestClient(client.app)
    assert public_client.get(f"/markdown/meeting-notes/{note_filename}.md").status_code == 404
    assert (
        public_client.get(
            f"/markdown/meeting-notes/sources/{note['id'][:8]}/original.txt"
        ).status_code
        == 404
    )

    assert client.get(f"/data/meeting-notes/{note_filename}.md").status_code == 404
    (tmp_path / "data" / "mia.db").write_text("private database", encoding="utf-8")
    (tmp_path / "data" / "system.db").write_text("private system database", encoding="utf-8")
    (tmp_path / "data" / "system.db-wal").write_text(
        "private system database sidecar",
        encoding="utf-8",
    )
    assert client.get("/mia.db").status_code == 404
    assert client.get("/system.db").status_code == 404
    assert client.get("/system.db-wal").status_code == 404


def test_get_note_normalizes_legacy_parser_markdown(client: TestClient, tmp_path: Path):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "legacy-parser@example.com",
            "name": "Legacy Parser User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    folder = client.post("/api/folders", json={"name": "Research"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "user_id": user["id"],
            "folder_id": folder["id"],
            "title": "Legacy OCR",
            "text": "Temporary text.",
        },
    ).json()
    note_filename = f"legacy-ocr-{note['id'][:8]}.md"
    note_path = tmp_path / "data" / "markdown" / "research" / note_filename
    note_path.write_text(
        "# Legacy OCR\n\n"
        "Created: 2026-05-24T00:00:00Z\n\n"
        "## Note\n\n"
        "*[Image OCR]\n"
        "| Left | Right |\n"
        "| --- | --- |\n"
        "| One<br>Two | <img src=\"diagram.png\"> |\n"
        "[End OCR]*\n"
        "```html\n"
        "<br>\n"
        "```\n",
        encoding="utf-8",
    )

    response = client.get(f"/api/notes/{note['id']}")

    assert response.status_code == 200
    assert response.json()["text"] == (
        "# Legacy OCR\n\n"
        "Created: 2026-05-24T00:00:00Z\n\n"
        "## Note\n\n"
        "| Left | Right |\n"
        "| --- | --- |\n"
        "| One<br />Two | <img src=\"diagram.png\" /> |\n"
        "```html\n"
        "<br>\n"
        "```"
    )
    assert note_path.read_text(encoding="utf-8") == response.json()["text"]


def test_update_note_moves_note_to_different_folder(client: TestClient, tmp_path: Path):
    client.post(
        "/api/auth/join",
        json={
            "email": "move-note@example.com",
            "name": "Move Note User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    inbox = client.post("/api/folders", json={"name": "Inbox"}).json()
    archive = client.post("/api/folders", json={"name": "Archive"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": inbox["id"],
            "title": "Move Me",
            "text": "This note should move folders.",
        },
    ).json()
    note_filename = f"move-me-{note['id'][:8]}.md"
    source_filename = f"sources/{note['id'][:8]}/original.txt"
    old_note_path = tmp_path / "data" / "markdown" / "inbox" / note_filename
    old_source_path = tmp_path / "data" / "markdown" / "inbox" / source_filename
    new_note_path = tmp_path / "data" / "markdown" / "archive" / note_filename
    new_source_path = tmp_path / "data" / "markdown" / "archive" / source_filename

    response = client.patch(
        f"/api/notes/{note['id']}",
        json={"folder_id": archive["id"]},
    )

    assert response.status_code == 200
    moved_note = response.json()
    assert moved_note["folder"]["id"] == archive["id"]
    assert moved_note["folder_id"] == archive["id"]
    assert moved_note["note_url"].endswith(f"/markdown/archive/{note_filename}")
    assert moved_note["source_files"][0]["url"].endswith(
        f"/markdown/archive/{source_filename}"
    )
    assert not old_note_path.exists()
    assert not old_source_path.exists()
    assert new_note_path.read_text(encoding="utf-8").startswith("# Move Me")
    assert new_source_path.read_text(encoding="utf-8") == "This note should move folders."

    old_folder_notes = client.get("/api/notes", params={"folder_id": inbox["id"]})
    new_folder_notes = client.get("/api/notes", params={"folder_id": archive["id"]})
    assert old_folder_notes.json() == []
    assert new_folder_notes.json()[0]["id"] == note["id"]


def test_updating_failed_note_clears_failed_status_and_console_job(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "failed-edit@example.com",
            "name": "Failed Edit User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Links"}).json()

    response = client.post(
        "/api/notes/from-url",
        json={
            "folder_id": folder["id"],
            "url": "https://www.youtube.com/watch?v=abc123",
        },
    )
    assert response.status_code == 201
    note = response.json()
    job_id = note["job_id"]

    with client.app.state.testing_session_factory() as session:
        db_note = session.get(Note, note["id"])
        db_job = session.get(MiaJob, job_id)
        assert db_note is not None
        assert db_job is not None
        db_note.status = "failed"
        db_job.status = "failed"
        db_job.error = job_runner.NO_YOUTUBE_SPEECH_MESSAGE
        session.commit()

    failed_note = client.get(f"/api/notes/{note['id']}").json()
    assert failed_note["status"] == "failed"
    assert failed_note["job_status"] == "failed"

    update_response = client.patch(
        f"/api/notes/{note['id']}",
        json={"text": "Manual notes about the chess position."},
    )

    assert update_response.status_code == 200
    updated_note = update_response.json()
    assert updated_note["status"] == "ready"
    assert updated_note["job_id"] is None
    assert updated_note["job_status"] is None
    assert "Manual notes about the chess position." in updated_note["text"]
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_create_empty_text_note_does_not_create_source_file(
    client: TestClient, tmp_path: Path
):
    client.post(
        "/api/auth/join",
        json={
            "email": "draft@example.com",
            "name": "Draft User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Drafts"}).json()

    response = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Draft Note",
            "text": "",
        },
    )

    assert response.status_code == 201
    note = response.json()
    note_filename = f"draft-note-{note['id'][:8]}"
    note_path = tmp_path / "data" / "markdown" / "drafts" / f"{note_filename}.md"
    source_dir = tmp_path / "data" / "markdown" / "drafts" / "sources" / note["id"][:8]

    assert note["source_type"] == "text"
    assert note["source_files"] == []
    assert note_path.exists()
    assert note_path.read_text(encoding="utf-8").startswith("# Draft Note")
    assert not source_dir.exists()

    listed = client.get("/api/notes", params={"folder_id": folder["id"]})
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == note["id"]
    assert listed.json()[0]["source_files"] == []


def test_get_note_returns_clear_error_when_markdown_file_is_missing(
    client: TestClient, tmp_path: Path
):
    client.post(
        "/api/auth/join",
        json={
            "email": "missing-file@example.com",
            "name": "Missing File User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Missing Files"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Missing Markdown",
            "text": "This file will be removed outside the app.",
        },
    ).json()
    note_path = (
        tmp_path
        / "data"
        / "markdown"
        / "missing-files"
        / f"missing-markdown-{note['id'][:8]}.md"
    )
    note_path.unlink()

    response = client.get(f"/api/notes/{note['id']}")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "This note still exists in the database, but its Markdown file no longer exists "
        "in the filesystem. It may have been deleted or moved outside Mianotes."
    )


def test_note_star_can_be_toggled_and_filtered(client: TestClient):
    admin = client.post(
        "/api/auth/join",
        json={
            "email": "star@example.com",
            "name": "Star User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    folder = client.post("/api/folders", json={"name": "Stars"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Important Note",
            "text": "This note should be easy to find later.",
        },
    ).json()

    starred = client.patch(f"/api/notes/{note['id']}/star", json={"is_starred": True})

    assert starred.status_code == 200
    assert starred.json()["is_starred"] is True
    assert starred.json()["updated_at"] == note["updated_at"]
    listed = client.get("/api/notes", params={"starred": True})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [note["id"]]
    assert listed.json()[0]["is_starred"] is True
    assert listed.json()[0]["updated_at"] == note["updated_at"]

    second_user = client.post(
        "/api/auth/join",
        json={
            "email": "other-star@example.com",
            "name": "Other Star User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    listed = client.get("/api/notes", params={"starred": True})
    assert listed.status_code == 200
    assert listed.json() == []
    visible_note = client.get(f"/api/notes/{note['id']}")
    assert visible_note.status_code == 200
    assert visible_note.json()["is_starred"] is False

    second_starred = client.patch(f"/api/notes/{note['id']}/star", json={"is_starred": True})
    assert second_starred.status_code == 200
    assert second_starred.json()["is_starred"] is True
    listed = client.get("/api/notes", params={"starred": True})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [note["id"]]

    client.post("/api/auth/login", json={"user_id": admin["id"], "password": "house-password"})
    unstarred = client.patch(f"/api/notes/{note['id']}/star", json={"is_starred": False})

    assert unstarred.status_code == 200
    assert unstarred.json()["is_starred"] is False
    assert unstarred.json()["updated_at"] == note["updated_at"]
    listed = client.get("/api/notes", params={"starred": True})
    assert listed.status_code == 200
    assert listed.json() == []

    client.post(
        "/api/auth/login",
        json={"user_id": second_user["id"], "password": "house-password"},
    )
    listed = client.get("/api/notes", params={"starred": True})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [note["id"]]


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
    folder = client.post(
        "/api/folders",
        json={"name": "Inbox"},
    ).json()

    response = client.post(
        "/api/notes",
        json={
            "user_id": user["id"],
            "folder_id": folder["id"],
            "text": "This note has no provided title, so the API infers one.",
        },
    )

    assert response.status_code == 201
    assert response.json()["title"] == "This note has no provided title, so the API infers one"


def test_note_summary_is_limited_to_55_words(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "summary@example.com",
            "name": "Summary User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Summaries"}).json()
    text = " ".join(f"word{i}" for i in range(70))

    response = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Long Summary",
            "text": text,
        },
    )

    assert response.status_code == 201
    summary = response.json()["summary"]
    assert len(summary.removesuffix("...").split()) == 55
    assert summary.endswith("...")


def test_list_notes_backfills_summary_from_note_body(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "backfill@example.com",
            "name": "Backfill User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Backfill"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Backfill title",
            "text": "The useful description should come from the note body.",
        },
    ).json()

    from mianotes_web_service.db.models import Note
    from mianotes_web_service.db.session import get_session

    with next(client.app.dependency_overrides[get_session]()) as session:
        db_note = session.get(Note, note["id"])
        assert db_note is not None
        db_note.summary = "Backfill title"
        session.commit()

    listed = client.get("/api/notes")
    assert listed.status_code == 200
    assert listed.json()[0]["summary"] == "The useful description should come from the note body."


def test_list_notes_backfills_stale_wrapped_summary(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "wrapped-summary@example.com",
            "name": "Wrapped Summary User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Wrapped Summary"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Wrapped title",
            "text": "Only this sentence should appear in the note list.",
        },
    ).json()

    from mianotes_web_service.db.models import Note
    from mianotes_web_service.db.session import get_session

    with next(client.app.dependency_overrides[get_session]()) as session:
        db_note = session.get(Note, note["id"])
        assert db_note is not None
        db_note.summary = (
            "Wrapped title Created: 2026 05 18T00:00:00Z Note "
            "Only this sentence should appear in the note list."
        )
        session.commit()

    listed = client.get("/api/notes")
    assert listed.status_code == 200
    assert listed.json()[0]["summary"] == "Only this sentence should appear in the note list."


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
    folder = client.post("/api/folders", json={"name": "Uploads"}).json()

    response = client.post(
        "/api/notes/from-file",
        data={"folder_id": folder["id"], "title": "Receipt"},
        files={"file": ("receipt.pdf", b"%PDF-1.4 test content", "application/pdf")},
    )

    assert response.status_code == 201
    note = response.json()
    assert note["user"]["id"] == user["id"]
    assert note["folder"]["id"] == folder["id"]
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
    assert "Your file has been added to the queue" in note["text"]
    note_filename = f"receipt-{note['id'][:8]}"
    assert note["note_url"].endswith(f"/markdown/uploads/{note_filename}.md")
    assert note["source_files"][0]["original_filename"] == "receipt.pdf"
    assert note["source_files"][0]["url"].endswith(
        f"/markdown/uploads/sources/{note['id'][:8]}/original.pdf"
    )

    listed = client.get("/api/notes")
    assert listed.status_code == 200
    listed_note = next(item for item in listed.json() if item["id"] == note["id"])
    assert listed_note["source_files"][0]["original_filename"] == "receipt.pdf"
    assert listed_note["source_files"][0]["url"].endswith(
        f"/markdown/uploads/sources/{note['id'][:8]}/original.pdf"
    )

    note_path = tmp_path / "data" / "markdown" / "uploads" / f"{note_filename}.md"
    source_path = (
        tmp_path
        / "data"
        / "markdown"
        / "uploads"
        / "sources"
        / note["id"][:8]
        / "original.pdf"
    )
    assert note_path.read_text(encoding="utf-8").startswith("# Receipt")
    assert source_path.read_bytes() == b"%PDF-1.4 test content"

    deleted = client.delete(f"/api/notes/{note['id']}")
    assert deleted.status_code == 204
    assert note_path.exists()
    assert source_path.exists()
    assert source_path.parent.exists()


def test_create_note_from_file_uses_requested_workspace_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_dir = tmp_path / "data"
    blog_dir = tmp_path / "blog"
    config_path = tmp_path / "workspaces.json"
    write_storage_config(
        config_path,
        StorageConfig(
            active_location="default",
            database_file=DEFAULT_DATABASE_FILE,
            locations=[
                StorageLocation(
                    id="default",
                    name="Main workspace",
                    folder_path=data_dir,
                ),
                StorageLocation(
                    id="blog",
                    name="Blog",
                    folder_path=blog_dir,
                ),
            ],
        ),
    )
    monkeypatch.setenv("MIANOTES_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MIANOTES_STORAGE_CONFIG_PATH", str(config_path))
    get_settings.cache_clear()

    class NoopJobRunner:
        def enqueue(self, background_tasks, job_id: str, workspace=None):
            pass

    app = create_app()
    with TestClient(app) as workspace_client:
        workspace_client.app.state.job_runner = NoopJobRunner()
        join_response = workspace_client.post(
            "/api/auth/join",
            json={
                "email": "workspace-upload@example.com",
                "name": "Workspace Upload User",
                "password": "house-password",
                "password_confirmation": "house-password",
            },
        )
        assert join_response.status_code == 201

        headers = {"X-Mianotes-Workspace": "blog"}
        folder = workspace_client.post(
            "/api/folders",
            json={"name": "Research"},
            headers=headers,
        ).json()
        response = workspace_client.post(
            "/api/notes/from-file",
            data={"folder_id": folder["id"], "title": "PM intro"},
            files={"file": ("pm-intro.txt", b"PM intro source", "text/plain")},
            headers=headers,
        )

        assert response.status_code == 201
        note = response.json()
        note_filename = f"pm-intro-{note['id'][:8]}.md"
        source_filename = f"sources/{note['id'][:8]}/original.txt"
        blog_note_path = blog_dir / "markdown" / "research" / note_filename
        blog_source_path = blog_dir / "markdown" / "research" / source_filename
        default_note_path = data_dir / "markdown" / "research" / note_filename
        default_source_path = data_dir / "markdown" / "research" / source_filename

        assert blog_note_path.read_text(encoding="utf-8").startswith("# PM intro")
        assert blog_source_path.read_bytes() == b"PM intro source"
        assert not default_note_path.exists()
        assert not default_source_path.exists()

        detail = workspace_client.get(f"/api/notes/{note['id']}", headers=headers)

        assert detail.status_code == 200
        assert "Your file has been added to the queue" in detail.json()["text"]
        assert detail.json()["note_url"].endswith(f"/markdown/research/{note_filename}")
        assert detail.json()["source_files"][0]["url"].endswith(
            f"/markdown/research/{source_filename}"
        )

    get_settings.cache_clear()


def test_upload_note_image_stores_file_for_editor(client: TestClient, tmp_path: Path):
    client.post(
        "/api/auth/join",
        json={
            "email": "editor-image@example.com",
            "name": "Editor Image User",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Editor Images"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Diagram note",
            "text": "This note needs a diagram.",
        },
    ).json()

    response = client.post(
        f"/api/notes/{note['id']}/images",
        files={"image": ("diagram.png", b"fake image bytes", "image/png")},
    )

    assert response.status_code == 201
    image_url = response.json()["url"]
    assert f"/markdown/editor-images/images/{note['id'][:8]}/diagram-" in image_url
    assert image_url.endswith(".png")
    image_response = client.get(image_url)
    assert image_response.status_code == 200
    assert image_response.content == b"fake image bytes"

    image_directory = tmp_path / "data" / "markdown" / "editor-images" / "images" / note["id"][:8]
    image_files = list(image_directory.glob("*.png"))
    assert len(image_files) == 1

    deleted = client.delete(f"/api/notes/{note['id']}")
    assert deleted.status_code == 204
    assert image_files[0].exists()
    assert image_files[0].parent.exists()


@pytest.mark.parametrize("filename", ["voice.mp3", "voice.m4a", "voice.wav"])
def test_create_note_from_file_accepts_audio_files(client: TestClient, filename: str):
    client.post(
        "/api/auth/join",
        json={
            "email": f"{Path(filename).stem}@example.com",
            "name": "Audio User",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Audio"}).json()

    response = client.post(
        "/api/notes/from-file",
        data={"folder_id": folder["id"], "title": "Voice note"},
        files={"file": (filename, b"audio bytes", "audio/mpeg")},
    )

    assert response.status_code == 201
    note = response.json()
    assert note["source_type"] == "audio"
    assert note["status"] == "pending_parse"


def test_create_note_from_file_requires_title(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "upload-title@example.com",
            "name": "Upload Title User",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Uploads"}).json()

    response = client.post(
        "/api/notes/from-file",
        data={"folder_id": folder["id"]},
        files={"file": ("receipt.pdf", b"%PDF-1.4 test content", "application/pdf")},
    )

    assert response.status_code == 422


def test_create_note_from_file_rejects_blank_title(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "upload-blank-title@example.com",
            "name": "Upload Blank Title User",
            "password": "instance-password",
            "password_confirmation": "instance-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Uploads"}).json()

    response = client.post(
        "/api/notes/from-file",
        data={"folder_id": folder["id"], "title": "   "},
        files={"file": ("receipt.pdf", b"%PDF-1.4 test content", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Title required"


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
    folder = client.post("/api/folders", json={"name": "Links"}).json()

    response = client.post(
        "/api/notes/from-url",
        json={
            "folder_id": folder["id"],
            "url": "https://example.com/articles/mianotes",
            "tags": ["research"],
        },
    )

    assert response.status_code == 201
    note = response.json()
    assert note["user"]["id"] == user["id"]
    assert note["folder"]["id"] == folder["id"]
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
    assert "Mia is indexing your link" in note["text"]

    note_filename = f"mianotes-{note['id'][:8]}"
    note_path = tmp_path / "data" / "markdown" / "links" / f"{note_filename}.md"
    source_path = (
        tmp_path
        / "data"
        / "markdown"
        / "links"
        / "sources"
        / note["id"][:8]
        / "original.html"
    )
    assert note_path.read_text(encoding="utf-8").startswith("# mianotes")
    assert note["source_files"][0]["original_filename"] == "https://example.com/articles/mianotes"
    assert note["source_files"][0]["url"].endswith(
        f"/markdown/links/sources/{note['id'][:8]}/original.html"
    )
    assert not source_path.exists()

    listed = client.get("/api/notes")
    assert listed.status_code == 200
    listed_note = next(item for item in listed.json() if item["id"] == note["id"])
    assert listed_note["source_files"][0]["original_filename"] == (
        "https://example.com/articles/mianotes"
    )
    assert listed_note["source_files"][0]["url"].endswith(
        f"/markdown/links/sources/{note['id'][:8]}/original.html"
    )


def test_create_note_from_url_preserves_remote_file_extension(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "pdf-url@example.com",
            "name": "PDF URL User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Remote PDFs"}).json()

    response = client.post(
        "/api/notes/from-url",
        json={
            "folder_id": folder["id"],
            "url": "https://cdn.openai.com/business-guides-and-resources/identifying-and-scaling-ai-use-cases.pdf",
        },
    )

    assert response.status_code == 201
    note = response.json()
    assert note["source_type"] == "link"
    assert note["source_files"][0]["original_filename"].endswith(
        "/identifying-and-scaling-ai-use-cases.pdf"
    )
    assert note["source_files"][0]["content_type"] == "application/pdf"
    assert note["source_files"][0]["url"].endswith(
        f"/markdown/remote-pdfs/sources/{note['id'][:8]}/original.pdf"
    )


def test_agent_created_url_job_includes_client(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "agent-job@example.com",
            "name": "Agent Job User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Agent Links"}).json()
    created_key = client.post("/api/settings/api-key", json={})
    raw_token = created_key.json()["token"]
    session_response = client.post(
        "/api/auth/agent-session",
        headers={
            "Authorization": f"Bearer {raw_token}",
            "X-Mianotes-Client": "Cursor",
        },
    )
    assert session_response.status_code == 201
    session_token = session_response.json()["token"]

    response = TestClient(client.app).post(
        "/api/notes/from-url",
        json={
            "folder_id": folder["id"],
            "url": "https://example.com/cursor-link",
        },
        headers={"Authorization": f"Bearer {session_token}"},
    )

    assert response.status_code == 201
    job = response.json()["job"]
    assert job["client"] == {"key": "cursor", "name": "Cursor"}
    listed_job = client.get(f"/api/jobs/{job['id']}").json()
    assert listed_job["client"] == {"key": "cursor", "name": "Cursor"}


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
    folder = client.post("/api/folders", json={"name": "Family"}).json()
    admin_note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
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
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    forbidden_update = client.patch(
        f"/api/notes/{admin_note['id']}",
        json={"title": "Maria Edit"},
    )
    assert forbidden_update.status_code == 403
    assert forbidden_update.json()["detail"] == "Only Admin or an admin can change this note."

    maria_note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Maria Note",
            "text": "Maria can add a note to a shared folder.",
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
    folder = client.post("/api/folders", json={"name": "Collaboration"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
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
            "folder_id": folder["id"],
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
    assert comment_body["type"] == "comment"
    assert comment_body["body"] == "This is useful for the next call."
    assert comment_body["user"]["id"] == user["id"]

    comments = client.get(f"/api/notes/{note['id']}/comments")
    assert comments.status_code == 200
    assert [item["body"] for item in comments.json()] == ["This is useful for the next call."]

    avatar_relative_path = Path(".profiles") / user["id"] / "avatar-seed.jpg"
    avatar_path = get_settings().data_dir / avatar_relative_path
    avatar_path.parent.mkdir(parents=True)
    avatar_path.write_bytes(b"shared-avatar")
    session_factory = client.app.state.testing_session_factory
    with session_factory() as session:
        db_user = session.get(User, user["id"])
        assert db_user is not None
        db_user.avatar_path = avatar_relative_path.as_posix()
        session.commit()

    shared = client.post(f"/api/notes/{note['id']}/share")
    assert shared.status_code == 200
    share_url = shared.json()["share_url"]
    assert "/api/notes/shared/" in share_url

    guest_note = TestClient(client.app).get(share_url.removeprefix("http://testserver"))
    assert guest_note.status_code == 200
    assert guest_note.json()["id"] == note["id"]
    assert guest_note.json()["share_url"] == share_url

    shared_avatar = TestClient(client.app).get(
        share_url.removeprefix("http://testserver") + "/avatar"
    )
    assert shared_avatar.status_code == 200
    assert shared_avatar.content == b"shared-avatar"

    disabled = client.delete(f"/api/notes/{note['id']}/share")
    assert disabled.status_code == 204
    guest_missing = TestClient(client.app).get(share_url.removeprefix("http://testserver"))
    assert guest_missing.status_code == 404
    avatar_missing = TestClient(client.app).get(
        share_url.removeprefix("http://testserver") + "/avatar"
    )
    assert avatar_missing.status_code == 404


def test_mia_comment_prompt_returns_markdown_without_saving_prompt_comment(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from mianotes_web_service.api import notes
    from mianotes_web_service.services.mia import MiaTextResult

    captured: dict[str, str] = {}

    def fake_prompt_markdown(*, title: str, markdown: str, prompt: str) -> MiaTextResult:
        captured["title"] = title
        captured["markdown"] = markdown
        captured["prompt"] = prompt
        return MiaTextResult(
            text="## Summary\n\nThis is the short version.",
            provider="test",
            model="test-model",
        )

    monkeypatch.setattr(notes, "prompt_markdown", fake_prompt_markdown)
    client.post(
        "/api/auth/join",
        json={
            "email": "mia-comment@example.com",
            "name": "Mia Comment User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Prompts"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Planning trip to Mallorca",
            "text": "Long text goes here.",
        },
    ).json()

    response = client.post(
        f"/api/notes/{note['id']}/comments",
        json={"body": "@mia summarise this text"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "prompt"
    assert body["prompt"] == "summarise this text"
    assert body["note_id"] == note["id"]
    assert body["text"] == "## Summary\n\nThis is the short version."
    assert body["format"] == "markdown"
    assert "comment" not in body
    assert captured["title"] == "Planning trip to Mallorca"
    assert captured["markdown"] == "Long text goes here."
    assert "# Planning trip to Mallorca" not in captured["markdown"]
    assert "Created:" not in captured["markdown"]
    assert "## Note" not in captured["markdown"]
    assert captured["prompt"] == "summarise this text"

    comments = client.get(f"/api/notes/{note['id']}/comments")
    assert comments.status_code == 200
    assert comments.json() == []


def test_mia_comment_prompt_can_use_unsaved_markdown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from mianotes_web_service.api import notes
    from mianotes_web_service.services.mia import MiaTextResult

    captured: dict[str, str] = {}

    def fake_prompt_markdown(*, title: str, markdown: str, prompt: str) -> MiaTextResult:
        captured["markdown"] = markdown
        captured["prompt"] = prompt
        return MiaTextResult(
            text="## Improved\n\nUse the draft text.",
            provider="test",
            model="test-model",
        )

    monkeypatch.setattr(notes, "prompt_markdown", fake_prompt_markdown)
    client.post(
        "/api/auth/join",
        json={
            "email": "mia-draft@example.com",
            "name": "Mia Draft User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Draft prompts"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Draft note",
            "text": "Saved text.",
        },
    ).json()

    response = client.post(
        f"/api/notes/{note['id']}/comments",
        json={
            "body": "@mia improve this",
            "markdown": "Unsaved draft text.",
        },
    )

    assert response.status_code == 200
    assert response.json()["text"] == "## Improved\n\nUse the draft text."
    assert captured["markdown"] == "Unsaved draft text."
    assert captured["prompt"] == "improve this"


def test_mia_comment_prompt_requires_prompt_text(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "empty-mia@example.com",
            "name": "Empty Mia User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Prompts"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Empty prompt",
            "text": "A note.",
        },
    ).json()

    response = client.post(
        f"/api/notes/{note['id']}/comments",
        json={"body": "@mia"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Mia prompt cannot be empty"


def test_mia_comment_prompt_failure_does_not_save_prompt_comment(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from mianotes_web_service.api import notes
    from mianotes_web_service.services.mia import MiaUnavailable

    def fake_prompt_markdown(**_kwargs):
        raise MiaUnavailable("OpenAI API key is not configured")

    monkeypatch.setattr(notes, "prompt_markdown", fake_prompt_markdown)
    client.post(
        "/api/auth/join",
        json={
            "email": "failed-mia-comment@example.com",
            "name": "Failed Mia Comment User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Failed prompts"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Failed prompt",
            "text": "A note.",
        },
    ).json()

    response = client.post(
        f"/api/notes/{note['id']}/comments",
        json={"body": "@mia summarise text"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "OpenAI API key is not configured"
    comments = client.get(f"/api/notes/{note['id']}/comments")
    assert comments.status_code == 200
    assert comments.json() == []
