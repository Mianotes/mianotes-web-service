from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db.models import Base, Note, SourceFile, Topic, User
from mianotes_web_service.services import job_runner
from mianotes_web_service.services.job_runner import InProcessJobRunner
from mianotes_web_service.services.jobs import create_job, decode_job_payload
from mianotes_web_service.services.mia import MiaTextResult
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
    note_path = tmp_path / "data" / "user" / "topic" / "note.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("# Pending\n\nWaiting.", encoding="utf-8")
    if source_path is not None:
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("source", encoding="utf-8")

    with testing_session() as session:
        user = User(email="runner@example.com", name="Runner", username="runner", is_admin=True)
        session.add(user)
        session.flush()
        topic = Topic(user_id=user.id, name="Topic", slug="topic")
        session.add(topic)
        session.flush()
        note = Note(
            user_id=user.id,
            topic_id=topic.id,
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
    source_path = tmp_path / "data" / "user" / "topic" / "note.source.txt"
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


def test_job_runner_summarises_note_with_openai_adapter(
    tmp_path: Path,
    monkeypatch,
):
    testing_session = _session_factory()
    note_id, _ = _seed_note(testing_session, tmp_path)

    monkeypatch.setattr(
        job_runner,
        "summarise_markdown",
        lambda *, title, markdown: MiaTextResult(
            text="## Summary\n\nA short useful summary.",
            provider="local",
            model="llama3.2",
        ),
    )
    with testing_session() as session:
        user = session.query(User).one()
        job = create_job(
            session,
            user,
            job_type="summarise",
            note_id=note_id,
            input_payload={"note_id": note_id},
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
        assert note.revision_number == 2
        assert "A short useful summary." in Path(note.note_path).read_text(encoding="utf-8")
        assert job.status == "succeeded"
        result = decode_job_payload(job.result_json)
        assert result["operation"] == "summarise"
        assert result["provider"] == "local"
        assert result["model"] == "llama3.2"
