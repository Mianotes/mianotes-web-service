from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import MiaJob, Note, SourceFile
from mianotes_web_service.services.job_note_updates import write_note_markdown
from mianotes_web_service.services.jobs import append_job_log, decode_job_payload
from mianotes_web_service.services.parsing import (
    fetch_url_to_file,
    fetch_url_to_html,
    is_youtube_url,
    parse_document,
    parse_html_document,
    parse_youtube_url,
)
from mianotes_web_service.services.paths import source_file_path
from mianotes_web_service.services.storage import summarize_text


class JobUseCase(Protocol):
    def run(self, session: Session, job: MiaJob) -> dict[str, object]: ...


@dataclass(frozen=True)
class JobDispatcher:
    handlers: dict[str, JobUseCase]

    @classmethod
    def default(cls) -> JobDispatcher:
        return cls(
            handlers={
                "parse_file": ParseFileJob(),
                "parse_url": ParseUrlJob(),
            }
        )

    def run(self, session: Session, job: MiaJob) -> dict[str, object]:
        handler = self.handlers.get(job.job_type)
        if handler is None:
            raise RuntimeError(f"Unsupported job type: {job.job_type}")
        return handler.run(session, job)


@dataclass(frozen=True)
class ParseFileJob:
    def run(self, session: Session, job: MiaJob) -> dict[str, object]:
        payload = decode_job_payload(job.input_json)
        note = job_note(session, job)
        source_file = job_source_file(session, payload)
        note.status = "parsing"
        session.flush()

        parsed = parse_document(source_file_path(source_file))
        append_job_log(
            job,
            command=f"finish {job.job_type} parsing",
            response=f"parsed {len(parsed.text)} characters with {parsed.parser}",
            status="succeeded",
        )
        session.commit()
        write_note_markdown(note, parsed.text)
        note.status = "ready"
        note.summary = summarize_text(parsed.text)
        return {
            "parser": parsed.parser,
            "source_file_id": source_file.id,
            "characters": len(parsed.text),
        }


@dataclass(frozen=True)
class ParseUrlJob:
    def run(self, session: Session, job: MiaJob) -> dict[str, object]:
        payload = decode_job_payload(job.input_json)
        url = payload.get("url")
        if not isinstance(url, str) or not url:
            raise RuntimeError("Job is missing url")

        note = job_note(session, job)
        source_file = job_source_file(session, payload)
        note.status = "parsing"
        session.flush()

        source_path = source_file_path(source_file)
        if is_youtube_url(url):
            parsed = parse_youtube_url(url)
        elif source_path.suffix.lower() not in {".htm", ".html"}:
            parsed = parse_document(fetch_url_to_file(url, source_path))
        else:
            parsed = parse_html_document(fetch_url_to_html(url, source_path), url=url)

        write_note_markdown(note, parsed.text)
        note.status = "ready"
        note.summary = summarize_text(parsed.text)
        return {
            "parser": parsed.parser,
            "source_file_id": source_file.id,
            "url": url,
            "characters": len(parsed.text),
        }


def job_note(session: Session, job: MiaJob) -> Note:
    if job.note_id is None:
        raise RuntimeError("Job is not associated with a note")
    note = session.get(Note, job.note_id)
    if note is None:
        raise RuntimeError("Note not found")
    return note


def job_source_file(session: Session, payload: dict[str, object]) -> SourceFile:
    source_file_id = payload.get("source_file_id")
    if not isinstance(source_file_id, str):
        raise RuntimeError("Job is missing source_file_id")
    source_file = session.get(SourceFile, source_file_id)
    if source_file is None:
        raise RuntimeError("Source file not found")
    return source_file
