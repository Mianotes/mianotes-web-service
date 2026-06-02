from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db.models import Base, Folder, Note, SourceFile, User
from mianotes_web_service.services import job_runner, job_use_cases, parsing
from mianotes_web_service.services.job_runner import InProcessJobRunner
from mianotes_web_service.services.jobs import (
    append_job_log,
    create_job,
    decode_job_log,
    decode_job_payload,
)
from mianotes_web_service.services.parsing import ParsedDocument
from mianotes_web_service.services.workspace_context import WorkspaceContext


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _seed_note(
    testing_session: sessionmaker[Session],
    tmp_path: Path,
    *,
    source_path: Path | None = None,
) -> tuple[str, str]:
    note_path = tmp_path / "data" / "user" / "folder" / "note.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("# Pending\n\nWaiting.", encoding="utf-8")
    if source_path is not None:
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("source", encoding="utf-8")

    with testing_session() as session:
        user = User(email="runner@example.com", name="Runner", username="runner", is_admin=True)
        session.add(user)
        session.flush()
        folder = Folder(user_id=user.id, name="Folder", slug="folder", path="folder")
        session.add(folder)
        session.flush()
        note = Note(
            user_id=user.id,
            folder_id=folder.id,
            title="Runner Note",
            status="pending_parse",
            source_type="document",
            note_path=str(note_path),
        )
        session.add(note)
        session.flush()
        source_file_id = ""
        if source_path is not None:
            source_file = SourceFile(
                note_id=note.id,
                file_path=str(source_path),
                original_filename=source_path.name,
                content_type="text/plain",
            )
            session.add(source_file)
            session.flush()
            source_file_id = source_file.id
        session.commit()
        return note.id, source_file_id


def test_job_runner_enqueue_uses_request_workspace(tmp_path: Path):
    runner = InProcessJobRunner(_session_factory())
    background_tasks = SimpleNamespace(calls=[])

    def add_task(func, *args):
        background_tasks.calls.append((func, args))

    background_tasks.add_task = add_task
    workspace = WorkspaceContext(
        id="blog",
        name="Blog",
        folder_path=tmp_path / "blog",
    )

    runner.enqueue(background_tasks, "job-id", workspace)

    assert background_tasks.calls == [(runner.run, ("job-id", workspace))]


def test_job_runner_parses_file_and_updates_note(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "original.txt"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)

    def fake_parse_document(path: Path) -> ParsedDocument:
        return ParsedDocument(text="Parsed Markdown", parser="markitdown", source_path=path)

    monkeypatch.setattr(job_use_cases, "parse_document", fake_parse_document)
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_file",
            note_id=note_id,
            input_payload={"source_file_id": source_file_id},
        )
        session.commit()
        job_id = job.id

    InProcessJobRunner(testing_session).run(job_id)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        assert note.status == "ready"
        assert "# Runner Note" in Path(note.note_path).read_text(encoding="utf-8")
        assert "Parsed Markdown" in Path(note.note_path).read_text(encoding="utf-8")
        assert job.status == "succeeded"
        assert decode_job_payload(job.result_json)["parser"] == "markitdown"
        assert decode_job_log(job.log_json) == []


def test_job_runner_parses_regular_url_with_html_fetch(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "page.html"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)
    fetched: list[str] = []

    def fake_fetch_url_to_html(url: str, output_path: Path):
        fetched.append(url)
        output_path.write_text("<html>Example</html>", encoding="utf-8")
        return output_path

    def fake_parse_html_document(path: Path, *, url: str | None = None) -> ParsedDocument:
        return ParsedDocument(text="Parsed HTML URL", parser="markitdown", source_path=path)

    monkeypatch.setattr(job_use_cases, "fetch_url_to_html", fake_fetch_url_to_html)
    monkeypatch.setattr(job_use_cases, "parse_html_document", fake_parse_html_document)
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_url",
            note_id=note_id,
            input_payload={
                "source_file_id": source_file_id,
                "url": "https://example.com/article",
            },
        )
        session.commit()
        job_id = job.id

    InProcessJobRunner(testing_session).run(job_id)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        assert fetched == ["https://example.com/article"]
        assert note.status == "ready"
        assert "Parsed HTML URL" in Path(note.note_path).read_text(encoding="utf-8")
        assert decode_job_payload(job.result_json)["parser"] == "markitdown"


def test_job_runner_parses_remote_file_url_as_document(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "original.pdf"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)
    fetched: list[tuple[str, Path]] = []
    parsed_paths: list[Path] = []

    def fake_fetch_url_to_file(url: str, output_path: Path):
        fetched.append((url, output_path))
        output_path.write_bytes(b"%PDF-1.4")
        return output_path

    def fake_parse_document(path: Path) -> ParsedDocument:
        parsed_paths.append(path)
        return ParsedDocument(text="Parsed PDF URL", parser="markitdown", source_path=path)

    monkeypatch.setattr(job_use_cases, "fetch_url_to_file", fake_fetch_url_to_file)
    monkeypatch.setattr(job_use_cases, "parse_document", fake_parse_document)
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_url",
            note_id=note_id,
            input_payload={
                "source_file_id": source_file_id,
                "url": "https://cdn.example.com/report.pdf",
            },
        )
        session.commit()
        job_id = job.id

    InProcessJobRunner(testing_session).run(job_id)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        assert fetched == [("https://cdn.example.com/report.pdf", source_path)]
        assert parsed_paths == [source_path]
        assert note.status == "ready"
        assert "Parsed PDF URL" in Path(note.note_path).read_text(encoding="utf-8")
        assert decode_job_payload(job.result_json)["parser"] == "markitdown"


def test_job_runner_parses_youtube_url_with_markitdown_url_converter(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "page.html"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)
    fetched: list[str] = []
    parsed_urls: list[str] = []

    def fake_fetch_url_to_html(url: str, output_path: Path):
        fetched.append(url)
        output_path.write_text("<html>Should not happen</html>", encoding="utf-8")
        return output_path

    def fake_parse_youtube_url(url: str) -> ParsedDocument:
        parsed_urls.append(url)
        return ParsedDocument(
            text="YouTube transcript text",
            parser="markitdown+youtube",
            source_path=Path(url),
        )

    monkeypatch.setattr(job_use_cases, "fetch_url_to_html", fake_fetch_url_to_html)
    monkeypatch.setattr(job_use_cases, "parse_youtube_url", fake_parse_youtube_url)
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_url",
            note_id=note_id,
            input_payload={
                "source_file_id": source_file_id,
                "url": "https://www.youtube.com/watch?v=abc123",
            },
        )
        session.commit()
        job_id = job.id

    InProcessJobRunner(testing_session).run(job_id)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        assert fetched == []
        assert parsed_urls == ["https://www.youtube.com/watch?v=abc123"]
        assert note.status == "ready"
        assert "YouTube transcript text" in Path(note.note_path).read_text(encoding="utf-8")
        assert decode_job_payload(job.result_json)["parser"] == "markitdown+youtube"


def test_job_runner_persists_partial_parser_text_updates(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "original.txt"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)
    note_path = tmp_path / "data" / "user" / "folder" / "note.md"
    partial_snapshots = []

    def fake_parse_document(path: Path) -> ParsedDocument:
        parsing._emit_parser_text_update("Chunk 1")
        partial_snapshots.append(note_path.read_text(encoding="utf-8"))
        return ParsedDocument(text="Chunk 1\n\nChunk 2", parser="markitdown", source_path=path)

    monkeypatch.setattr(job_use_cases, "parse_document", fake_parse_document)
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_file",
            note_id=note_id,
            input_payload={"source_file_id": source_file_id},
        )
        session.commit()
        job_id = job.id

    InProcessJobRunner(testing_session).run(job_id)

    assert partial_snapshots
    assert "Chunk 1" in partial_snapshots[0]
    assert "Chunk 2" not in partial_snapshots[0]
    final_text = note_path.read_text(encoding="utf-8")
    assert "Chunk 1" in final_text
    assert "Chunk 2" in final_text


def test_job_runner_keeps_logs_for_failed_jobs(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "original.txt"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)

    def fake_parse_document(path: Path) -> ParsedDocument:
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(job_use_cases, "parse_document", fake_parse_document)
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_file",
            note_id=note_id,
            input_payload={"source_file_id": source_file_id},
        )
        session.commit()
        job_id = job.id

    InProcessJobRunner(testing_session).run(job_id)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        assert note.status == "failed"
        text = Path(note.note_path).read_text(encoding="utf-8")
        assert "Mia couldn't process this file." in text
        assert "Your file has been added to the queue" not in text
        assert f"[Console](/jobs?job={job_id}) screen" in text
        assert "Jobs screen" not in text
        assert "parser exploded" not in text
        assert job.status == "failed"
        assert job.error == "parser exploded"
        log = decode_job_log(job.log_json)
        assert log[0]["command"] == "start parse_file"
        assert log[-1]["command"] == "finish parse_file"
        assert log[-1]["response"] == "parser exploded"


def test_job_runner_links_failed_url_notes_to_console_job(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "page.html"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)

    def fake_fetch_url_to_html(url: str, output_path: Path):
        raise RuntimeError("link parser exploded")

    monkeypatch.setattr(job_use_cases, "fetch_url_to_html", fake_fetch_url_to_html)
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_url",
            note_id=note_id,
            input_payload={
                "source_file_id": source_file_id,
                "url": "https://example.com/article",
            },
        )
        session.commit()
        job_id = job.id

    InProcessJobRunner(testing_session).run(job_id)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        text = Path(note.note_path).read_text(encoding="utf-8")
        assert "Mia couldn't process this link." in text
        assert (
            "The link has been saved, but Mia could not turn it into a note this time."
            in text
        )
        assert f"[Console](/jobs?job={job_id}) screen" in text
        assert "Jobs screen" not in text
        assert "link parser exploded" not in text
        assert job.status == "failed"
        assert job.error == "link parser exploded"


def test_job_runner_shows_safe_failed_url_reason_in_note(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "page.html"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)

    def fake_parse_youtube_url(url: str) -> ParsedDocument:
        raise RuntimeError(job_runner.NO_YOUTUBE_SPEECH_MESSAGE)

    monkeypatch.setattr(job_use_cases, "parse_youtube_url", fake_parse_youtube_url)
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_url",
            note_id=note_id,
            input_payload={
                "source_file_id": source_file_id,
                "url": "https://www.youtube.com/watch?v=abc123",
            },
        )
        session.commit()
        job_id = job.id

    InProcessJobRunner(testing_session).run(job_id)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        text = Path(note.note_path).read_text(encoding="utf-8")
        assert "Mia couldn't process this link." in text
        assert job_runner.NO_YOUTUBE_SPEECH_MESSAGE in text
        assert (
            "The link has been saved, but Mia could not turn it into a note this time."
            not in text
        )
        assert f"[Console](/jobs?job={job_id}) screen" in text
        assert job.status == "failed"
        assert job.error == job_runner.NO_YOUTUBE_SPEECH_MESSAGE


def test_job_runner_marks_job_failed_when_finalization_crashes(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "original.txt"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)

    def fake_parse_document(path: Path) -> ParsedDocument:
        return ParsedDocument(text="Parsed Markdown", parser="markitdown", source_path=path)

    def fake_mark_job_succeeded(*_args, **_kwargs):
        raise RuntimeError("success marker exploded")

    monkeypatch.setattr(job_use_cases, "parse_document", fake_parse_document)
    monkeypatch.setattr(job_runner, "mark_job_succeeded", fake_mark_job_succeeded)
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_file",
            note_id=note_id,
            input_payload={"source_file_id": source_file_id},
        )
        session.commit()
        job_id = job.id

    InProcessJobRunner(testing_session).run(job_id)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        assert note.status == "failed"
        assert job.status == "failed"
        assert job.error == "success marker exploded"
        log = decode_job_log(job.log_json)
        assert log[-1]["command"] == "finish parse_file"
        assert log[-1]["response"] == "Job runner crashed: success marker exploded"


def test_fail_interrupted_jobs_marks_running_jobs_failed(
    tmp_path: Path,
):
    testing_session = _session_factory()
    note_id, source_file_id = _seed_note(testing_session, tmp_path)

    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_file",
            note_id=note_id,
            input_payload={"source_file_id": source_file_id},
        )
        job.status = "running"
        session.commit()
        job_id = job.id

    with testing_session() as session:
        job_runner.fail_interrupted_jobs(session)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        assert note.status == "failed"
        assert job.status == "failed"
        assert job.error == job_runner.INTERRUPTED_JOB_MESSAGE
        log = decode_job_log(job.log_json)
        assert log[-1]["command"] == "finish parse_file"
        assert log[-1]["response"] == job_runner.INTERRUPTED_JOB_MESSAGE


def test_fail_interrupted_jobs_reports_last_running_step(
    tmp_path: Path,
):
    testing_session = _session_factory()
    note_id, source_file_id = _seed_note(testing_session, tmp_path)

    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="parse_file",
            note_id=note_id,
            input_payload={"source_file_id": source_file_id},
        )
        job.status = "running"
        append_job_log(
            job,
            command="MarkItDown.convert(original.pdf) with plugins/options",
            response="started",
            status="running",
        )
        session.commit()
        job_id = job.id

    with testing_session() as session:
        job_runner.fail_interrupted_jobs(session)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        expected = (
            "Mia was interrupted while running "
            "`MarkItDown.convert(original.pdf) with plugins/options`. "
            "Please upload the file again."
        )
        assert note.status == "failed"
        assert job.status == "failed"
        assert job.error == expected
        text = Path(note.note_path).read_text(encoding="utf-8")
        assert "Mia couldn't process this file." in text
        log = decode_job_log(job.log_json)
        assert log[-1]["command"] == "finish parse_file"
        assert log[-1]["response"] == expected


def test_fail_interrupted_jobs_recreates_missing_note_parent(
    tmp_path: Path,
):
    testing_session = _session_factory()
    note_id, source_file_id = _seed_note(testing_session, tmp_path)

    with testing_session() as session:
        user = session.query(User).one()
        note = session.get(Note, note_id)
        assert note is not None
        note.note_path = str(tmp_path / "missing" / "folder" / "queued.md")
        job = create_job(
            session,
            user,
            job_type="parse_file",
            note_id=note_id,
            input_payload={"source_file_id": source_file_id},
        )
        job.status = "queued"
        session.commit()
        job_id = job.id

    with testing_session() as session:
        job_runner.fail_interrupted_jobs(session)

    with testing_session() as session:
        note = session.get(Note, note_id)
        job = session.get(job_runner.MiaJob, job_id)
        assert note is not None
        assert job is not None
        note_path = Path(note.note_path)
        assert note.status == "failed"
        assert job.status == "failed"
        assert note_path.exists()
        assert "Mia couldn't process this file." in note_path.read_text(encoding="utf-8")
