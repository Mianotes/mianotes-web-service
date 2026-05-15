from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import MiaJob, User

JOB_STATUSES = frozenset({"queued", "running", "succeeded", "failed", "cancelled"})


def encode_job_payload(payload: Mapping[str, object] | None) -> str:
    return json.dumps(payload or {}, sort_keys=True)


def decode_job_payload(payload: str) -> dict[str, object]:
    try:
        loaded = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


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
    )
    session.add(job)
    return job


def mark_job_running(job: MiaJob) -> None:
    job.status = "running"
    job.started_at = datetime.now(UTC)


def mark_job_succeeded(job: MiaJob, result: Mapping[str, object] | None = None) -> None:
    job.status = "succeeded"
    job.result_json = encode_job_payload(result)
    job.finished_at = datetime.now(UTC)


def mark_job_failed(job: MiaJob, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.finished_at = datetime.now(UTC)


def cancel_job(job: MiaJob) -> None:
    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
