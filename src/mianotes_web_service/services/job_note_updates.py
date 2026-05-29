from __future__ import annotations

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import MiaJob, Note
from mianotes_web_service.services.parser_youtube import NO_YOUTUBE_SPEECH_MESSAGE
from mianotes_web_service.services.paths import note_file_path
from mianotes_web_service.services.storage import render_markdown_note, summarize_text

FAILED_FILE_MESSAGE = (
    "Mia couldn't process this file.\n\n"
    "The file has been saved, but Mia could not turn it into a note this time. "
    "You can check the {console_link} screen for the technical details."
)
FAILED_LINK_MESSAGE = (
    "Mia couldn't process this link.\n\n"
    "The link has been saved, but Mia could not turn it into a note this time. "
    "You can check the {console_link} screen for the technical details."
)
FAILED_LINK_WITH_REASON_MESSAGE = (
    "Mia couldn't process this link.\n\n"
    "{reason}\n\n"
    "You can check the {console_link} screen for the technical details."
)
USER_SAFE_FAILURE_REASONS = frozenset({NO_YOUTUBE_SPEECH_MESSAGE})
NOTE_JOB_TYPES = frozenset({"parse_file", "parse_url"})


def write_note_markdown(note: Note, text: str) -> None:
    path = note_file_path(note)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_markdown_note(title=note.title, text=text),
        encoding="utf-8",
    )


def mark_note_failed(job: MiaJob, *, failure_reason: str | None = None) -> None:
    if job.note is None or job.job_type not in NOTE_JOB_TYPES:
        return

    job.note.status = "failed"
    message = _failure_message(job, failure_reason=failure_reason)
    write_note_markdown(job.note, message)
    job.note.summary = summarize_text(message)


def persist_note_text_update(session: Session, job_id: str, text: str) -> None:
    job = session.get(MiaJob, job_id)
    if job is None or job.note is None or job.job_type not in NOTE_JOB_TYPES:
        return

    job.note.status = "parsing"
    write_note_markdown(job.note, text)
    job.note.summary = summarize_text(text)
    session.commit()


def _failure_message(job: MiaJob, *, failure_reason: str | None) -> str:
    console_link = f"[Console](/jobs?job={job.id})"
    if job.job_type == "parse_url" and failure_reason in USER_SAFE_FAILURE_REASONS:
        return FAILED_LINK_WITH_REASON_MESSAGE.format(
            console_link=console_link,
            reason=failure_reason,
        )

    message_template = (
        FAILED_LINK_MESSAGE if job.job_type == "parse_url" else FAILED_FILE_MESSAGE
    )
    return message_template.format(console_link=console_link)
