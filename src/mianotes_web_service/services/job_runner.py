from __future__ import annotations

from collections.abc import Callable

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session, sessionmaker

from mianotes_web_service.db.models import MiaJob
from mianotes_web_service.services.job_interruption import (
    INTERRUPTED_JOB_MESSAGE,
    fail_interrupted_jobs,
)
from mianotes_web_service.services.job_note_updates import (
    mark_note_failed,
    persist_note_text_update,
)
from mianotes_web_service.services.job_use_cases import JobDispatcher
from mianotes_web_service.services.jobs import (
    append_job_log,
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
)
from mianotes_web_service.services.parser_types import PartialParseError
from mianotes_web_service.services.parser_youtube import NO_YOUTUBE_SPEECH_MESSAGE
from mianotes_web_service.services.parsing import (
    parser_job_logging,
    parser_text_updates,
)
from mianotes_web_service.services.workspace_context import (
    WorkspaceContext,
    current_workspace,
    reset_current_workspace,
    set_current_workspace,
)

__all__ = [
    "INTERRUPTED_JOB_MESSAGE",
    "InProcessJobRunner",
    "MiaJob",
    "NO_YOUTUBE_SPEECH_MESSAGE",
    "fail_interrupted_jobs",
]


class InProcessJobRunner:
    def __init__(
        self,
        session_factory: (
            sessionmaker[Session]
            | Callable[[WorkspaceContext], sessionmaker[Session]]
        ),
        dispatcher: JobDispatcher | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.dispatcher = dispatcher or JobDispatcher.default()

    def enqueue(
        self,
        background_tasks: BackgroundTasks,
        job_id: str,
        workspace: WorkspaceContext | None = None,
    ) -> None:
        background_tasks.add_task(
            self.run,
            job_id,
            workspace if workspace is not None else current_workspace(),
        )

    def _session_factory(self, workspace: WorkspaceContext | None) -> sessionmaker[Session]:
        if isinstance(self.session_factory, sessionmaker):
            return self.session_factory
        if workspace is None:
            from mianotes_web_service.db.workspace_routing import default_workspace

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
                    lambda text: persist_note_text_update(session, job_id, text)
                ):
                    result = self.dispatcher.run(session, job)
        except Exception as exc:  # pragma: no cover - defensive boundary
            session.rollback()
            failed_job = session.get(MiaJob, job_id)
            if failed_job is not None:
                if isinstance(exc, PartialParseError):
                    mark_note_failed(
                        failed_job,
                        failure_reason=str(exc),
                        partial_text=exc.partial_text,
                        partial_failure_message=exc.partial_failure_message,
                    )
                else:
                    mark_note_failed(failed_job, failure_reason=str(exc))
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


def _mark_job_crashed(session: Session, job_id: str, exc: Exception) -> None:
    job = session.get(MiaJob, job_id)
    if job is None or job.status not in {"queued", "running"}:
        return
    try:
        mark_note_failed(job)
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
