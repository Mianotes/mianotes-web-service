from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session, sessionmaker

from mianotes_web_service.db.models import MiaJob, Note, SourceFile
from mianotes_web_service.services.jobs import (
    decode_job_payload,
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
)
from mianotes_web_service.services.mia import summarise_markdown
from mianotes_web_service.services.parsing import fetch_url_to_html, parse_document
from mianotes_web_service.services.storage import render_markdown_note


class InProcessJobRunner:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def enqueue(self, background_tasks: BackgroundTasks, job_id: str) -> None:
        background_tasks.add_task(self.run, job_id)

    def run(self, job_id: str) -> None:
        try:
            with self.session_factory() as session:
                self._run_with_session(session, job_id)
        except Exception:
            return

    def _run_with_session(self, session: Session, job_id: str) -> None:
        job = session.get(MiaJob, job_id)
        if job is None or job.status != "queued":
            return
        mark_job_running(job)
        session.commit()

        try:
            result = _run_job(session, job)
        except Exception as exc:  # pragma: no cover - defensive boundary
            session.rollback()
            failed_job = session.get(MiaJob, job_id)
            if failed_job is not None:
                _mark_note_failed(failed_job)
                mark_job_failed(failed_job, str(exc))
                session.commit()
            return

        mark_job_succeeded(job, result)
        session.commit()


def _run_job(session: Session, job: MiaJob) -> dict[str, object]:
    if job.job_type == "parse_file":
        return _run_parse_file_job(session, job)
    if job.job_type == "parse_url":
        return _run_parse_url_job(session, job)
    if job.job_type == "summarise":
        return _run_summarise_job(session, job)
    raise RuntimeError(f"Unsupported job type: {job.job_type}")


def _job_note(session: Session, job: MiaJob) -> Note:
    if job.note_id is None:
        raise RuntimeError("Job is not associated with a note")
    note = session.get(Note, job.note_id)
    if note is None:
        raise RuntimeError("Note not found")
    return note


def _job_source_file(session: Session, payload: dict[str, object]) -> SourceFile:
    source_file_id = payload.get("source_file_id")
    if not isinstance(source_file_id, str):
        raise RuntimeError("Job is missing source_file_id")
    source_file = session.get(SourceFile, source_file_id)
    if source_file is None:
        raise RuntimeError("Source file not found")
    return source_file


def _run_parse_file_job(session: Session, job: MiaJob) -> dict[str, object]:
    payload = decode_job_payload(job.input_json)
    note = _job_note(session, job)
    source_file = _job_source_file(session, payload)
    note.status = "parsing"
    session.flush()

    parsed = parse_document(Path(source_file.file_path))
    Path(note.note_path).write_text(
        render_markdown_note(title=note.title, text=parsed.text),
        encoding="utf-8",
    )
    note.status = "ready"
    return {
        "parser": parsed.parser,
        "source_file_id": source_file.id,
        "characters": len(parsed.text),
    }


def _run_parse_url_job(session: Session, job: MiaJob) -> dict[str, object]:
    payload = decode_job_payload(job.input_json)
    url = payload.get("url")
    if not isinstance(url, str) or not url:
        raise RuntimeError("Job is missing url")

    note = _job_note(session, job)
    source_file = _job_source_file(session, payload)
    note.status = "parsing"
    session.flush()

    html_path = fetch_url_to_html(url, Path(source_file.file_path))
    parsed = parse_document(html_path)
    Path(note.note_path).write_text(
        render_markdown_note(title=note.title, text=parsed.text),
        encoding="utf-8",
    )
    note.status = "ready"
    return {
        "parser": parsed.parser,
        "source_file_id": source_file.id,
        "url": url,
        "characters": len(parsed.text),
    }


def _run_summarise_job(session: Session, job: MiaJob) -> dict[str, object]:
    note = _job_note(session, job)
    note_path = Path(note.note_path)
    summary = summarise_markdown(title=note.title, markdown=note_path.read_text(encoding="utf-8"))
    note_path.write_text(
        render_markdown_note(title=note.title, text=summary),
        encoding="utf-8",
    )
    note.revision_number += 1
    note.status = "ready"
    return {
        "provider": "openai",
        "operation": "summarise",
        "characters": len(summary),
    }


def _mark_note_failed(job: MiaJob) -> None:
    if job.note is not None and job.job_type in {"parse_file", "parse_url"}:
        job.note.status = "failed"
