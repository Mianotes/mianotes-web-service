from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import joinedload, selectinload

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.db.models import MiaJob, User
from mianotes_web_service.domain.schemas import AgentClientRead, MiaJobListItem, MiaJobListPage, MiaJobRead
from mianotes_web_service.services.jobs import decode_job_log, decode_job_payload

router = APIRouter(prefix="/jobs", tags=["jobs"])
RECENT_SUCCEEDED_JOB_WINDOW = timedelta(hours=24)
DEFAULT_JOBS_LIMIT = 50
MAX_JOBS_LIMIT = 200


def _ensure_can_read_job(job: MiaJob, user: User) -> None:
    if user.is_admin or job.user_id == user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot read this job")


def _job_response(job: MiaJob) -> MiaJobRead:
    return MiaJobRead(
        id=job.id,
        user=job.user,
        client=(
            AgentClientRead(key=job.client_key, name=job.client_name)
            if job.client_key and job.client_name
            else None
        ),
        note_id=job.note_id,
        note_title=job.note.title if job.note is not None else None,
        job_type=job.job_type,
        status=job.status,
        input=decode_job_payload(job.input_json),
        result=decode_job_payload(job.result_json),
        log=decode_job_log(job.log_json),
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _job_list_item(
    job: MiaJob,
    *,
    include_logs: bool = False,
    include_payloads: bool = False,
) -> MiaJobListItem:
    return MiaJobListItem(
        id=job.id,
        user=job.user,
        client=(
            AgentClientRead(key=job.client_key, name=job.client_name)
            if job.client_key and job.client_name
            else None
        ),
        note_id=job.note_id,
        note_title=job.note.title if job.note is not None else None,
        job_type=job.job_type,
        status=job.status,
        input=decode_job_payload(job.input_json) if include_payloads else None,
        result=decode_job_payload(job.result_json) if include_payloads else None,
        log=decode_job_log(job.log_json) if include_logs else None,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _encode_job_cursor(job: MiaJob) -> str:
    payload = {"created_at": job.created_at.isoformat(), "id": job.id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _decode_job_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
        created_at = datetime.fromisoformat(payload["created_at"])
        job_id = str(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid jobs cursor",
        ) from exc
    return created_at, job_id


@router.get("", response_model=MiaJobListPage)
def list_jobs(
    session: SessionDep,
    user: NotesReadUser,
    note_id: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_JOBS_LIMIT)] = DEFAULT_JOBS_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
    include_logs: Annotated[bool, Query()] = False,
    include_payloads: Annotated[bool, Query()] = False,
) -> MiaJobListPage:
    recent_succeeded_cutoff = datetime.now(UTC) - RECENT_SUCCEEDED_JOB_WINDOW
    statement = (
        select(MiaJob)
        .options(selectinload(MiaJob.user), selectinload(MiaJob.note))
        .where(
            or_(
                MiaJob.status.in_(("queued", "running", "failed")),
                (MiaJob.status == "succeeded")
                & (MiaJob.finished_at.is_not(None))
                & (MiaJob.finished_at >= recent_succeeded_cutoff),
            )
        )
        .order_by(MiaJob.created_at.desc(), MiaJob.id.desc())
    )
    if not user.is_admin:
        statement = statement.where(MiaJob.user_id == user.id)
    if note_id is not None:
        statement = statement.where(MiaJob.note_id == note_id)
    if status_filter is not None:
        statement = statement.where(MiaJob.status == status_filter)
    if cursor:
        cursor_created_at, cursor_id = _decode_job_cursor(cursor)
        statement = statement.where(
            or_(
                MiaJob.created_at < cursor_created_at,
                and_(MiaJob.created_at == cursor_created_at, MiaJob.id < cursor_id),
            )
        )

    jobs = list(session.scalars(statement.limit(limit + 1)).all())
    has_next_page = len(jobs) > limit
    page_jobs = jobs[:limit]
    return MiaJobListPage(
        items=[
            _job_list_item(
                job,
                include_logs=include_logs,
                include_payloads=include_payloads,
            )
            for job in page_jobs
        ],
        limit=limit,
        next_cursor=_encode_job_cursor(page_jobs[-1]) if has_next_page and page_jobs else None,
    )


@router.get("/{job_id}", response_model=MiaJobRead)
def get_job(job_id: str, session: SessionDep, user: NotesReadUser) -> MiaJobRead:
    job = session.scalars(
        select(MiaJob)
        .where(MiaJob.id == job_id)
        .options(joinedload(MiaJob.note))
    ).one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _ensure_can_read_job(job, user)
    return _job_response(job)
