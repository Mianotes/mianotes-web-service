from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import MiaJob, User

JOB_STATUSES = frozenset({"queued", "running", "succeeded", "failed", "cancelled"})
MAX_JOB_LOG_ENTRIES = 60
MAX_JOB_LOG_FIELD_LENGTH = 1200


def encode_job_payload(payload: Mapping[str, object] | None) -> str:
    return json.dumps(payload or {}, sort_keys=True)


def decode_job_payload(payload: str) -> dict[str, object]:
    try:
        loaded = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def decode_job_log(payload: str) -> list[dict[str, object]]:
    try:
        loaded = json.loads(payload or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def append_job_log(
    job: MiaJob,
    *,
    command: str,
    response: str | None = None,
    status: str = "info",
) -> None:
    entries = decode_job_log(job.log_json)
    entries.append(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": status,
            "command": _limit_log_field(command),
            "response": _limit_log_field(response) if response is not None else None,
        }
    )
    job.log_json = json.dumps(entries[-MAX_JOB_LOG_ENTRIES:], sort_keys=True)


def _limit_log_field(value: str) -> str:
    if len(value) <= MAX_JOB_LOG_FIELD_LENGTH:
        return value
    return f"{value[:MAX_JOB_LOG_FIELD_LENGTH]}..."


def create_job(
    session: Session,
    user: User,
    *,
    job_type: str,
    note_id: str | None = None,
    input_payload: Mapping[str, object] | None = None,
) -> MiaJob:
    job = MiaJob(
        user_id=user.id,
        note_id=note_id,
        job_type=job_type,
        status="queued",
        input_json=encode_job_payload(input_payload),
        result_json="{}",
        log_json="[]",
    )
    session.add(job)
    return job


def mark_job_running(job: MiaJob) -> None:
    job.status = "running"
    job.started_at = datetime.now(UTC)


def mark_job_succeeded(job: MiaJob, result: Mapping[str, object] | None = None) -> None:
    job.status = "succeeded"
    job.result_json = encode_job_payload(result)
    job.log_json = "[]"
    job.finished_at = datetime.now(UTC)


def mark_job_failed(job: MiaJob, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.finished_at = datetime.now(UTC)


def cancel_job(job: MiaJob) -> None:
    job.status = "cancelled"
    job.log_json = "[]"
    job.finished_at = datetime.now(UTC)
