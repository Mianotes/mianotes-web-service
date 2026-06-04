from collections.abc import Generator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.api.note_access import (
    read_note_for_change,
    read_note_for_response,
)
from mianotes_web_service.api.note_ingestion import _enqueue_job
from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Base, MiaJob, Note, SourceFile, Tag, User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.services import job_runner
from mianotes_web_service.services.storage_settings import (
    StorageConfig,
    StorageLocation,
    write_storage_config,
)
from mianotes_web_service.services.workspace_context import WorkspaceContext


def _png_bytes(size: tuple[int, int] = (16, 16)) -> bytes:
    image_bytes = BytesIO()
    Image.new("RGB", size, "#1684ff").save(image_bytes, format="PNG")
    return image_bytes.getvalue()


def _allow_url_ingestion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mianotes_web_service.api.note_ingestion.validate_fetch_url",
        lambda url: None,
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


@contextmanager
def _record_sql(engine):
    statements: list[str] = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.lower().split()))

    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)


def _create_note_with_related_rows(client: TestClient, *, email_prefix: str = "loader") -> dict:
    user = client.post(
        "/api/auth/join",
        json={
            "email": f"{email_prefix}@example.com",
            "name": "Loader User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    folder = client.post("/api/folders", json={"name": "Loader Notes"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Loader Graph",
            "text": "This note has related rows for loader tests.",
            "tags": ["initial"],
        },
    ).json()

    session_factory = client.app.state.testing_session_factory
    with session_factory() as session:
        db_note = session.get(Note, note["id"])
        assert db_note is not None
        first_tag = session.query(Tag).filter_by(slug="initial").one()
        second_tag = Tag(name="Performance", slug="performance")
        db_note.tags = [first_tag, second_tag]
        session.add_all(
            [
                SourceFile(
                    note_id=note["id"],
                    filename="original.txt",
                    file_path="/tmp/original.txt",
                    original_filename="original.txt",
                    content_type="text/plain",
                ),
                SourceFile(
                    note_id=note["id"],
                    filename="extra.txt",
                    file_path="/tmp/extra.txt",
                    original_filename="extra.txt",
                    content_type="text/plain",
                ),
                MiaJob(
                    user_id=user["id"],
                    note_id=note["id"],
                    job_type="parse_file",
                    status="queued",
                ),
                MiaJob(
                    user_id=user["id"],
                    note_id=note["id"],
                    job_type="parse_file",
                    status="succeeded",
                ),
            ]
        )
        session.commit()
    return note


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
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(job_runner=FakeJobRunner()))
    )
    session = SimpleNamespace(info={"workspace": workspace})

    _enqueue_job(request, background_tasks, "job-id", session)

    assert calls == [(background_tasks, "job-id", workspace)]


def test_note_response_loader_uses_separate_collection_queries(client: TestClient):
    note = _create_note_with_related_rows(client)
    session_factory = client.app.state.testing_session_factory
    with session_factory() as session:
        engine = session.get_bind()

    with _record_sql(engine) as statements:
        with session_factory() as session:
            loaded_note = read_note_for_response(session, note["id"])
            assert loaded_note.user.name == "Loader User"
            assert loaded_note.folder.name == "Loader Notes"
            assert len(loaded_note.source_files) == 3
            assert {tag.slug for tag in loaded_note.tags} == {"initial", "performance"}
            assert len(loaded_note.jobs) == 2

    main_note_selects = [
        statement
        for statement in statements
        if " from notes " in statement and "where notes.id =" in statement
    ]
    assert len(main_note_selects) == 1
    main_note_select = main_note_selects[0]
    for collection_table in ("source_files", "note_tags", "mia_jobs"):
        assert collection_table not in main_note_select
    assert any(" from source_files " in statement for statement in statements)
    assert any(" join note_tags " in statement for statement in statements)
    assert any(" from mia_jobs " in statement for statement in statements)


def test_note_change_loader_does_not_load_child_collections(client: TestClient):
    note = _create_note_with_related_rows(client, email_prefix="change-loader")
    session_factory = client.app.state.testing_session_factory
    with session_factory() as session:
        engine = session.get_bind()

    with _record_sql(engine) as statements:
        with session_factory() as session:
            loaded_note = read_note_for_change(session, note["id"])
            assert loaded_note.user.name == "Loader User"
            assert loaded_note.folder.name == "Loader Notes"

    main_note_selects = [
        statement
        for statement in statements
        if " from notes " in statement and "where notes.id =" in statement
    ]
    assert len(main_note_selects) == 1
    for statement in statements:
        assert "source_files" not in statement
        assert "note_tags" not in statement
        assert "mia_jobs" not in statement


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
    assert listed.json()["items"][0]["id"] == note["id"]
    assert listed.json()["items"][0]["status"] == "ready"
    assert listed.json()["items"][0]["source_type"] == "text"
    assert listed.json()["items"][0]["is_starred"] is False
    assert (
        listed.json()["items"][0]["summary"]
        == "We agreed to build Mianotes with Markdown notes."
    )
    assert listed.json()["items"][0]["filename"] == f"{note_filename}.md"
    assert "text" not in listed.json()["items"][0]

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
    (tmp_path / "data" / "workspace.db").write_text("private database", encoding="utf-8")
    (tmp_path / "data" / "system.db").write_text("private system database", encoding="utf-8")
    (tmp_path / "data" / "system.db-wal").write_text(
        "private system database sidecar",
        encoding="utf-8",
    )
    assert client.get("/workspace.db").status_code == 404
    assert client.get("/system.db").status_code == 404
    assert client.get("/system.db-wal").status_code == 404


def test_list_notes_uses_cursor_pagination_without_default_counts(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "pagination@example.com",
            "name": "Pagination User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Pagination"}).json()
    notes = [
        client.post(
            "/api/notes/from-text",
            json={
                "folder_id": folder["id"],
                "title": f"Paged note {index}",
                "text": f"Body for note {index}",
            },
        ).json()
        for index in range(3)
    ]
    first_page = client.get("/api/notes", params={"folder_id": folder["id"], "limit": 2})

    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert first_payload["total"] is None
    assert first_payload["limit"] == 2
    assert first_payload["next_cursor"]
    assert len(first_payload["items"]) == 2
    assert first_payload["counts"] is None

    second_page = client.get(
        "/api/notes",
        params={"folder_id": folder["id"], "limit": 2, "cursor": first_payload["next_cursor"]},
    )

    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["total"] is None
    assert second_payload["next_cursor"] is None
    assert len(second_payload["items"]) == 1
    returned_ids = {item["id"] for item in first_payload["items"] + second_payload["items"]}
    assert returned_ids == {note["id"] for note in notes}


def test_list_notes_can_include_total_and_counts_when_requested(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "pagination-meta@example.com",
            "name": "Pagination Meta User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Pagination Meta"}).json()
    for index in range(3):
        client.post(
            "/api/notes/from-text",
            json={
                "folder_id": folder["id"],
                "title": f"Paged meta note {index}",
                "text": f"Body for note {index}",
            },
        )

    response = client.get(
        "/api/notes",
        params={
            "folder_id": folder["id"],
            "limit": 2,
            "include_total": "true",
            "include_counts": "true",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["counts"]["folders"][folder["id"]] == 3


def test_folder_counts_are_available_without_listing_notes(client: TestClient):
    client.post(
        "/api/auth/join",
        json={
            "email": "folder-counts@example.com",
            "name": "Folder Counts User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    first_folder = client.post("/api/folders", json={"name": "Counts One"}).json()
    second_folder = client.post("/api/folders", json={"name": "Counts Two"}).json()
    for index in range(2):
        client.post(
            "/api/notes/from-text",
            json={
                "folder_id": first_folder["id"],
                "title": f"First folder note {index}",
                "text": "Body",
            },
        )
    client.post(
        "/api/notes/from-text",
        json={
            "folder_id": second_folder["id"],
            "title": "Second folder note",
            "text": "Body",
        },
    )

    response = client.get("/api/folders/counts")

    assert response.status_code == 200
    counts = response.json()["folders"]
    assert counts[first_folder["id"]] == 2
    assert counts[second_folder["id"]] == 1


def test_delete_note_removes_markdown_file(client: TestClient, tmp_path: Path):
    client.post(
        "/api/auth/join",
        json={
            "email": "delete-note@example.com",
            "name": "Delete Note User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Delete Notes"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Delete me",
            "text": "This Markdown file should be deleted with the note.",
        },
    ).json()
    note_path = (
        tmp_path
        / "data"
        / "markdown"
        / "delete-notes"
        / f"delete-me-{note['id'][:8]}.md"
    )
    assert note_path.exists()

    response = client.delete(f"/api/notes/{note['id']}")

    assert response.status_code == 204
    assert not note_path.exists()
    assert client.get(f"/api/notes/{note['id']}").status_code == 404


def test_delete_note_succeeds_when_markdown_file_is_already_missing(
    client: TestClient,
    tmp_path: Path,
):
    client.post(
        "/api/auth/join",
        json={
            "email": "missing-note@example.com",
            "name": "Missing Note User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Missing Notes"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Already gone",
            "text": "The file disappears before the DB row is deleted.",
        },
    ).json()
    note_path = (
        tmp_path
        / "data"
        / "markdown"
        / "missing-notes"
        / f"already-gone-{note['id'][:8]}.md"
    )
    note_path.unlink()

    response = client.delete(f"/api/notes/{note['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/notes/{note['id']}").status_code == 404


def test_delete_note_does_not_remove_paths_outside_markdown_root(
    client: TestClient,
    tmp_path: Path,
):
    client.post(
        "/api/auth/join",
        json={
            "email": "outside-path@example.com",
            "name": "Outside Path User",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Outside Paths"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Outside path",
            "text": "This note record points outside the managed Markdown tree.",
        },
    ).json()
    outside_path = tmp_path / "outside-note.md"
    outside_path.write_text("# Outside\n", encoding="utf-8")
    with client.app.state.testing_session_factory() as session:
        db_note = session.get(Note, note["id"])
        assert db_note is not None
        db_note.filename = None
        db_note.note_path = str(outside_path)
        session.commit()

    response = client.delete(f"/api/notes/{note['id']}")

    assert response.status_code == 204
    assert outside_path.exists()
    assert client.get(f"/api/notes/{note['id']}").status_code == 404


def test_get_note_normalizes_parser_markdown(client: TestClient, tmp_path: Path):
    user = client.post(
        "/api/auth/join",
        json={
            "email": "parser@example.com",
            "name": "Parser User",
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
            "title": "Parser OCR",
            "text": "Temporary text.",
        },
    ).json()
    note_filename = f"parser-ocr-{note['id'][:8]}.md"
    note_path = tmp_path / "data" / "markdown" / "research" / note_filename
    note_path.write_text(
        "# Parser OCR\n\n"
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
        "# Parser OCR\n\n"
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
    assert old_folder_notes.json()["items"] == []
    assert new_folder_notes.json()["items"][0]["id"] == note["id"]


def test_updating_failed_note_clears_failed_status_and_console_job(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _allow_url_ingestion(monkeypatch)
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
    assert listed.json()["items"][0]["id"] == note["id"]
    assert listed.json()["items"][0]["source_files"] == []


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
    assert [item["id"] for item in listed.json()["items"]] == [note["id"]]
    assert listed.json()["items"][0]["is_starred"] is True
    assert listed.json()["items"][0]["updated_at"] == note["updated_at"]

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
    assert listed.json()["items"] == []
    visible_note = client.get(f"/api/notes/{note['id']}")
    assert visible_note.status_code == 200
    assert visible_note.json()["is_starred"] is False

    second_starred = client.patch(f"/api/notes/{note['id']}/star", json={"is_starred": True})
    assert second_starred.status_code == 200
    assert second_starred.json()["is_starred"] is True
    listed = client.get("/api/notes", params={"starred": True})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [note["id"]]

    client.post("/api/auth/login", json={"user_id": admin["id"], "password": "house-password"})
    unstarred = client.patch(f"/api/notes/{note['id']}/star", json={"is_starred": False})

    assert unstarred.status_code == 200
    assert unstarred.json()["is_starred"] is False
    assert unstarred.json()["updated_at"] == note["updated_at"]
    listed = client.get("/api/notes", params={"starred": True})
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    client.post(
        "/api/auth/login",
        json={"user_id": second_user["id"], "password": "house-password"},
    )
    listed = client.get("/api/notes", params={"starred": True})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [note["id"]]


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


def test_list_notes_does_not_backfill_summary_from_note_body(client: TestClient):
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
    assert listed.json()["items"][0]["summary"] == "Backfill title"

    with next(client.app.dependency_overrides[get_session]()) as session:
        db_note = session.get(Note, note["id"])
        assert db_note is not None
        assert db_note.summary == "Backfill title"


def test_list_notes_does_not_rewrite_stale_wrapped_summary(client: TestClient):
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
    assert listed.json()["items"][0]["summary"] == (
        "Wrapped title Created: 2026 05 18T00:00:00Z Note "
        "Only this sentence should appear in the note list."
    )

    with next(client.app.dependency_overrides[get_session]()) as session:
        db_note = session.get(Note, note["id"])
        assert db_note is not None
        assert db_note.summary == (
            "Wrapped title Created: 2026 05 18T00:00:00Z Note "
            "Only this sentence should appear in the note list."
        )


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
    listed_note = next(item for item in listed.json()["items"] if item["id"] == note["id"])
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
    assert not note_path.exists()
    assert source_path.exists()
    assert source_path.parent.exists()


def test_create_note_from_file_rejects_oversized_upload(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MIANOTES_MAX_UPLOAD_BYTES", "5")
    get_settings.cache_clear()
    client.post(
        "/api/auth/join",
        json={
            "email": "too-big-upload@example.com",
            "name": "Too Big Upload",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Uploads"}).json()

    response = client.post(
        "/api/notes/from-file",
        data={"folder_id": folder["id"], "title": "Oversized"},
        files={"file": ("oversized.txt", b"123456", "text/plain")},
    )

    assert response.status_code == 413
    assert not list((tmp_path / "data" / "markdown" / "uploads").glob("oversized-*.md"))
    get_settings.cache_clear()


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

        headers = {"X-Mianotes-Workspace": "Blog"}
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

        text_response = workspace_client.post(
            "/api/notes/from-text",
            json={
                "folder_id": folder["id"],
                "title": "Workspace markdown source",
                "text": "This is the raw Markdown body.",
            },
            headers=headers,
        )
        assert text_response.status_code == 201
        text_note = text_response.json()

        markdown_source = workspace_client.get(
            f"/api/workspaces/blog/markdown/{text_note['id']}"
        )
        assert markdown_source.status_code == 200
        assert markdown_source.headers["content-disposition"].startswith("inline;")
        assert markdown_source.headers["content-type"].startswith("text/plain")
        assert markdown_source.text.startswith("# Workspace markdown source")
        assert "This is the raw Markdown body." in markdown_source.text

        public_markdown_source = TestClient(workspace_client.app).get(
            f"/api/workspaces/blog/markdown/{text_note['id']}"
        )
        assert public_markdown_source.status_code == 401

        shared = workspace_client.post(f"/api/notes/{note['id']}/share", headers=headers)
        assert shared.status_code == 200
        share_path = shared.json()["share_url"].removeprefix("http://testserver")
        assert share_path.startswith("/api/notes/shared/workspaces/blog/")

        from mianotes_web_service.api import note_sharing

        opened_workspace_ids: list[str] = []
        original_sessionmaker_for_workspace = note_sharing.sessionmaker_for_workspace

        def tracking_sessionmaker_for_workspace(workspace):
            opened_workspace_ids.append(workspace.id)
            return original_sessionmaker_for_workspace(workspace)

        monkeypatch.setattr(
            note_sharing,
            "sessionmaker_for_workspace",
            tracking_sessionmaker_for_workspace,
        )

        guest_client = TestClient(workspace_client.app)
        guest_detail = guest_client.get(share_path)
        assert guest_detail.status_code == 200
        assert guest_detail.json()["text"].startswith("# PM intro")
        assert guest_detail.json()["note_url"].endswith(f"/markdown/research/{note_filename}")
        assert opened_workspace_ids == ["blog"]

        shared_source_url = guest_detail.json()["source_files"][0]["url"]
        assert shared_source_url.startswith("http://testserver/api/notes/shared/workspaces/blog/")

        opened_workspace_ids.clear()
        shared_source = guest_client.get(shared_source_url.removeprefix("http://testserver"))
        assert shared_source.status_code == 200
        assert shared_source.content == b"PM intro source"
        assert opened_workspace_ids == ["blog"]

        opened_workspace_ids.clear()
        missing_share = guest_client.get("/api/notes/shared/workspaces/blog/not-a-real-token")
        assert missing_share.status_code == 404
        assert opened_workspace_ids == ["blog"]

        opened_workspace_ids.clear()
        legacy_missing_share = guest_client.get("/api/notes/shared/not-a-real-token")
        assert legacy_missing_share.status_code == 404
        assert opened_workspace_ids == []

        unknown_workspace_share = guest_client.get(
            "/api/notes/shared/workspaces/missing/not-a-real-token"
        )
        assert unknown_workspace_share.status_code == 404
        assert opened_workspace_ids == []

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
        files={"image": ("diagram.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 201
    image_url = response.json()["url"]
    assert f"/markdown/editor-images/images/{note['id'][:8]}/diagram-" in image_url
    assert image_url.endswith(".png")
    image_response = client.get(image_url)
    assert image_response.status_code == 200
    assert image_response.content.startswith(b"\x89PNG")

    image_directory = tmp_path / "data" / "markdown" / "editor-images" / "images" / note["id"][:8]
    image_files = list(image_directory.glob("*.png"))
    assert len(image_files) == 1

    deleted = client.delete(f"/api/notes/{note['id']}")
    assert deleted.status_code == 204
    note_filename = f"diagram-note-{note['id'][:8]}.md"
    assert not (tmp_path / "data" / "markdown" / "editor-images" / note_filename).exists()
    assert image_files[0].exists()
    assert image_files[0].parent.exists()


def test_upload_note_image_rejects_oversized_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MIANOTES_MAX_EDITOR_IMAGE_BYTES", "5")
    get_settings.cache_clear()
    client.post(
        "/api/auth/join",
        json={
            "email": "editor-image-too-large@example.com",
            "name": "Editor Image Too Large",
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
        files={"image": ("diagram.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 413
    get_settings.cache_clear()


def test_upload_note_image_rejects_too_many_pixels(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MIANOTES_MAX_IMAGE_PIXELS", "10")
    get_settings.cache_clear()
    client.post(
        "/api/auth/join",
        json={
            "email": "editor-image-too-many-pixels@example.com",
            "name": "Editor Image Too Many Pixels",
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
        files={"image": ("diagram.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 413
    get_settings.cache_clear()


@pytest.mark.parametrize("filename", ["voice.mp3", "voice.m4a", "voice.wav", "voice.mp4"])
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
        files={
            "file": (
                filename,
                b"audio bytes",
                "video/mp4" if filename.endswith(".mp4") else "audio/mpeg",
            )
        },
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


def test_create_note_from_url_queues_parse_job(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _allow_url_ingestion(monkeypatch)
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
    listed_note = next(item for item in listed.json()["items"] if item["id"] == note["id"])
    assert listed_note["source_files"][0]["original_filename"] == (
        "https://example.com/articles/mianotes"
    )
    assert listed_note["source_files"][0]["url"].endswith(
        f"/markdown/links/sources/{note['id'][:8]}/original.html"
    )


def test_create_note_from_url_preserves_remote_file_extension(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _allow_url_ingestion(monkeypatch)
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


def test_agent_created_url_job_includes_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _allow_url_ingestion(monkeypatch)
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


def test_note_tags_and_share_link(client: TestClient):
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
    assert {"research", "summer-2026"}.issubset(
        {tag["slug"] for tag in listed_tags.json()}
    )

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
    assert "/api/notes/shared/workspaces/default/" in share_url

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


def test_non_admin_user_can_share_readable_note_without_editing_it(client: TestClient):
    admin = client.post(
        "/api/auth/join",
        json={
            "email": "share-admin@example.com",
            "name": "Share Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    folder = client.post("/api/folders", json={"name": "Open source"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder["id"],
            "title": "Theming and customisation",
            "text": "Shared workspace context.",
        },
    ).json()

    member = client.post(
        "/api/auth/join",
        json={
            "email": "share-member@example.com",
            "name": "Share Member",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    ).json()["user"]
    assert member["is_admin"] is False

    shared = client.post(f"/api/notes/{note['id']}/share")
    assert shared.status_code == 200
    share_url = shared.json()["share_url"]
    assert "/api/notes/shared/workspaces/default/" in share_url

    guest_note = TestClient(client.app).get(share_url.removeprefix("http://testserver"))
    assert guest_note.status_code == 200
    assert guest_note.json()["id"] == note["id"]

    disabled_by_member = client.delete(f"/api/notes/{note['id']}/share")
    assert disabled_by_member.status_code == 403
    assert (
        disabled_by_member.json()["detail"]
        == "Only Share Admin or an admin can change this note."
    )

    client.post("/api/auth/login", json={"user_id": admin["id"], "password": "house-password"})
    disabled_by_admin = client.delete(f"/api/notes/{note['id']}/share")
    assert disabled_by_admin.status_code == 204


def test_mia_prompt_returns_markdown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from mianotes_web_service.api import note_prompts
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

    monkeypatch.setattr(note_prompts, "prompt_markdown", fake_prompt_markdown)
    client.post(
        "/api/auth/join",
        json={
            "email": "mia-prompt@example.com",
            "name": "Mia Prompt User",
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
        f"/api/notes/{note['id']}/prompt",
        json={"prompt": "summarise this text"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "prompt"
    assert body["prompt"] == "summarise this text"
    assert body["note_id"] == note["id"]
    assert body["text"] == "## Summary\n\nThis is the short version."
    assert body["format"] == "markdown"
    assert captured["title"] == "Planning trip to Mallorca"
    assert captured["markdown"] == "Long text goes here."
    assert "# Planning trip to Mallorca" not in captured["markdown"]
    assert "Created:" not in captured["markdown"]
    assert "## Note" not in captured["markdown"]
    assert captured["prompt"] == "summarise this text"


def test_mia_prompt_can_use_unsaved_markdown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from mianotes_web_service.api import note_prompts
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

    monkeypatch.setattr(note_prompts, "prompt_markdown", fake_prompt_markdown)
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
        f"/api/notes/{note['id']}/prompt",
        json={
            "prompt": "improve this",
            "markdown": "Unsaved draft text.",
        },
    )

    assert response.status_code == 200
    assert response.json()["text"] == "## Improved\n\nUse the draft text."
    assert captured["markdown"] == "Unsaved draft text."
    assert captured["prompt"] == "improve this"


def test_mia_prompt_requires_prompt_text(client: TestClient):
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
        f"/api/notes/{note['id']}/prompt",
        json={"prompt": ""},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Mia prompt cannot be empty"


def test_mia_prompt_failure_returns_provider_message(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from mianotes_web_service.api import note_prompts
    from mianotes_web_service.services.mia import MiaUnavailable

    def fake_prompt_markdown(**_kwargs):
        raise MiaUnavailable("LLM key is not configured")

    monkeypatch.setattr(note_prompts, "prompt_markdown", fake_prompt_markdown)
    client.post(
        "/api/auth/join",
        json={
            "email": "failed-mia-prompt@example.com",
            "name": "Failed Mia Prompt User",
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
        f"/api/notes/{note['id']}/prompt",
        json={"prompt": "summarise text"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Mia needs an AI provider before it can answer prompts."
