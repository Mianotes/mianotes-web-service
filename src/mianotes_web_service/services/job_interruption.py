from __future__ import annotations

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import MiaJob
from mianotes_web_service.services.job_note_updates import mark_note_failed
from mianotes_web_service.services.jobs import (
    append_job_log,
    decode_job_log,
    mark_job_failed,
)

INTERRUPTED_JOB_MESSAGE = (
    "The service stopped before this job finished. Please upload the file again."
)
INTERRUPTED_JOB_WITH_STEP_MESSAGE = (
    "Mia was interrupted while running `{command}`. "
    "Please upload the file again."
)


def fail_interrupted_jobs(session: Session) -> None:
    jobs = (
        session.query(MiaJob)
        .filter(MiaJob.status.in_(("queued", "running")))
        .order_by(MiaJob.created_at.asc())
        .all()
    )
    for job in jobs:
        message = interrupted_job_message(job)
        mark_note_failed(job, failure_reason=message)
        append_job_log(
            job,
            command=f"finish {job.job_type}",
            response=message,
            status="failed",
        )
        mark_job_failed(job, message)
    if jobs:
        session.commit()


def interrupted_job_message(job: MiaJob) -> str:
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
