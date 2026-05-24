from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db.models import Base, Folder, Note, SourceFile, User
from mianotes_web_service.services import job_runner
from mianotes_web_service.services.job_runner import InProcessJobRunner
from mianotes_web_service.services.jobs import create_job, decode_job_log, decode_job_payload
from mianotes_web_service.services.parsing import ParsedDocument


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


def test_job_runner_parses_file_and_updates_note(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "original.txt"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)

    def fake_parse_document(path: Path) -> ParsedDocument:
        return ParsedDocument(text="Parsed Markdown", parser="markitdown", source_path=path)

    monkeypatch.setattr(job_runner, "parse_document", fake_parse_document)
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


def test_job_runner_keeps_logs_for_failed_jobs(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    source_path = tmp_path / "data" / "folder" / "sources" / "note1234" / "original.txt"
    note_id, source_file_id = _seed_note(testing_session, tmp_path, source_path=source_path)

    def fake_parse_document(path: Path) -> ParsedDocument:
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(job_runner, "parse_document", fake_parse_document)
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
        assert "Mia couldn’t process this file." in text
        assert "Your file has been added to the queue" not in text
        assert "Jobs screen" in text
        assert "parser exploded" not in text
        assert job.status == "failed"
        assert job.error == "parser exploded"
        log = decode_job_log(job.log_json)
        assert log[0]["command"] == "start parse_file"
        assert log[-1]["command"] == "finish parse_file"
        assert log[-1]["response"] == "parser exploded"
