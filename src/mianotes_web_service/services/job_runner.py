from __future__ import annotations

from collections.abc import Callable

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session, sessionmaker

from mianotes_web_service.db.models import MiaJob, Note, SourceFile
from mianotes_web_service.services.jobs import (
    append_job_log,
    decode_job_log,
    decode_job_payload,
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
)
from mianotes_web_service.services.parser_youtube import NO_YOUTUBE_SPEECH_MESSAGE
from mianotes_web_service.services.parsing import (
    fetch_url_to_file,
    fetch_url_to_html,
    is_youtube_url,
    parse_document,
    parse_html_document,
    parse_youtube_url,
    parser_job_logging,
    parser_text_updates,
)
from mianotes_web_service.services.paths import note_file_path, source_file_path
from mianotes_web_service.services.storage import render_markdown_note, summarize_text
from mianotes_web_service.services.workspace_context import (
    WorkspaceContext,
    current_workspace,
    reset_current_workspace,
    set_current_workspace,
)

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
INTERRUPTED_JOB_MESSAGE = (
    "The service stopped before this job finished. Please upload the file again."
)
INTERRUPTED_JOB_WITH_STEP_MESSAGE = (
    "Mia was interrupted while running `{command}`. "
    "Please upload the file again."
)


class InProcessJobRunner:
    def __init__(
        self,
        session_factory: (
            sessionmaker[Session]
            | Callable[[WorkspaceContext], sessionmaker[Session]]
        ),
    ) -> None:
        self.session_factory = session_factory

    def enqueue(self, background_tasks: BackgroundTasks, job_id: str) -> None:
        background_tasks.add_task(self.run, job_id, current_workspace())

    def _session_factory(self, workspace: WorkspaceContext | None) -> sessionmaker[Session]:
        if isinstance(self.session_factory, sessionmaker):
            return self.session_factory
        if workspace is None:
            from mianotes_web_service.db.session import default_workspace

            workspace = default_workspace()
        return self.session_factory(workspace)

    def run(self, job_id: str, workspace: WorkspaceContext | None = None) -> None:
        context_token = set_current_workspace(workspace) if workspace is not None else None
        try:
            with self._session_factory(workspace)() as session:
                self._run_with_session(session, job_id)
        except Exception as exc:
            with self._session_factory(workspace)() as session:
                _mark_job_crashed(session, job_id, exc)
            return
        finally:
            if context_token is not None:
                reset_current_workspace(context_token)

    def _run_with_session(self, session: Session, job_id: str) -> None:
        job = session.get(MiaJob, job_id)
        if job is None or job.status != "queued":
            return
        mark_job_running(job)
        append_job_log(job, command=f"start {job.job_type}", response="job is running")
        session.commit()

        try:
            with parser_job_logging(
                lambda command, response, status: _persist_job_log(
                    session,
                    job_id,
                    command,
                    response,
                    status,
                )
            ):
                with parser_text_updates(
                    lambda text: _persist_note_text_update(session, job_id, text)
                ):
                    result = _run_job(session, job)
        except Exception as exc:  # pragma: no cover - defensive boundary
            session.rollback()
            failed_job = session.get(MiaJob, job_id)
            if failed_job is not None:
                _mark_note_failed(failed_job, failure_reason=str(exc))
                append_job_log(
                    failed_job,
                    command=f"finish {failed_job.job_type}",
                    response=str(exc),
                    status="failed",
                )
                mark_job_failed(failed_job, str(exc))
                session.commit()
            return

        mark_job_succeeded(job, result)
        session.commit()


def fail_interrupted_jobs(session: Session) -> None:
    jobs = (
        session.query(MiaJob)
        .filter(MiaJob.status.in_(("queued", "running")))
        .order_by(MiaJob.created_at.asc())
        .all()
    )
    for job in jobs:
        message = _interrupted_job_message(job)
        _mark_note_failed(job, failure_reason=message)
        append_job_log(
            job,
            command=f"finish {job.job_type}",
            response=message,
            status="failed",
        )
        mark_job_failed(job, message)
    if jobs:
        session.commit()


def _interrupted_job_message(job: MiaJob) -> str:
    for entry in reversed(decode_job_log(job.log_json)):
        if entry.get("status") != "running":
            continue
        command = entry.get("command")
        if not isinstance(command, str) or not command:
            continue
        if command.startswith("start "):
            continue
        return INTERRUPTED_JOB_WITH_STEP_MESSAGE.format(command=command)
    return INTERRUPTED_JOB_MESSAGE


def _run_job(session: Session, job: MiaJob) -> dict[str, object]:
    if job.job_type == "parse_file":
        return _run_parse_file_job(session, job)
    if job.job_type == "parse_url":
        return _run_parse_url_job(session, job)
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

    parsed = parse_document(source_file_path(source_file))
    append_job_log(
        job,
        command=f"finish {job.job_type} parsing",
        response=f"parsed {len(parsed.text)} characters with {parsed.parser}",
        status="succeeded",
    )
    session.commit()
    note_file_path(note).write_text(
        render_markdown_note(title=note.title, text=parsed.text),
        encoding="utf-8",
    )
    note.status = "ready"
    note.summary = summarize_text(parsed.text)
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

    if is_youtube_url(url):
        parsed = parse_youtube_url(url)
    elif source_file_path(source_file).suffix.lower() not in {".htm", ".html"}:
        source_path = fetch_url_to_file(url, source_file_path(source_file))
        parsed = parse_document(source_path)
    else:
        html_path = fetch_url_to_html(url, source_file_path(source_file))
        parsed = parse_html_document(html_path, url=url)
    note_file_path(note).write_text(
        render_markdown_note(title=note.title, text=parsed.text),
        encoding="utf-8",
    )
    note.status = "ready"
    note.summary = summarize_text(parsed.text)
    return {
        "parser": parsed.parser,
        "source_file_id": source_file.id,
        "url": url,
        "characters": len(parsed.text),
    }


def _mark_note_failed(job: MiaJob, *, failure_reason: str | None = None) -> None:
    if job.note is not None and job.job_type in {"parse_file", "parse_url"}:
        job.note.status = "failed"
        console_link = f"[Console](/jobs?job={job.id})"
        if (
            job.job_type == "parse_url"
            and failure_reason in USER_SAFE_FAILURE_REASONS
        ):
            message = FAILED_LINK_WITH_REASON_MESSAGE.format(
                console_link=console_link,
                reason=failure_reason,
            )
        else:
            message_template = (
                FAILED_LINK_MESSAGE if job.job_type == "parse_url" else FAILED_FILE_MESSAGE
            )
            message = message_template.format(console_link=console_link)
        note_file_path(job.note).write_text(
            render_markdown_note(title=job.note.title, text=message),
            encoding="utf-8",
        )
        job.note.summary = summarize_text(message)


def _persist_note_text_update(session: Session, job_id: str, text: str) -> None:
    job = session.get(MiaJob, job_id)
    if job is None or job.note is None or job.job_type not in {"parse_file", "parse_url"}:
        return
    job.note.status = "parsing"
    note_file_path(job.note).write_text(
        render_markdown_note(title=job.note.title, text=text),
        encoding="utf-8",
    )
    job.note.summary = summarize_text(text)
    session.commit()


def _mark_job_crashed(session: Session, job_id: str, exc: Exception) -> None:
    job = session.get(MiaJob, job_id)
    if job is None or job.status not in {"queued", "running"}:
        return
    try:
        _mark_note_failed(job)
    except Exception:
        pass
    append_job_log(
        job,
        command=f"finish {job.job_type}",
        response=f"Job runner crashed: {exc}",
        status="failed",
    )
    mark_job_failed(job, str(exc))
    session.commit()


def _persist_job_log(
    session: Session,
    job_id: str,
    command: str,
    response: str | None,
    status: str,
) -> None:
    job = session.get(MiaJob, job_id)
    if job is None:
        return
    append_job_log(job, command=command, response=response, status=status)
    session.commit()
