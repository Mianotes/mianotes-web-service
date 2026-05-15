from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.db.models import MiaJob, User
from mianotes_web_service.domain.schemas import MiaJobRead
from mianotes_web_service.services.jobs import decode_job_payload

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _ensure_can_read_job(job: MiaJob, user: User) -> None:
    if user.is_admin or job.user_id == user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot read this job")


def _job_response(job: MiaJob) -> MiaJobRead:
    return MiaJobRead(
        id=job.id,
        user=job.user,
        note_id=job.note_id,
        job_type=job.job_type,
        status=job.status,
        input=decode_job_payload(job.input_json),
        result=decode_job_payload(job.result_json),
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("", response_model=list[MiaJobRead])
def list_jobs(
    session: SessionDep,
    user: NotesReadUser,
    note_id: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[MiaJobRead]:
    statement = (
        select(MiaJob)
        .options(joinedload(MiaJob.user))
        .order_by(MiaJob.created_at.desc())
    )
    if not user.is_admin:
        statement = statement.where(MiaJob.user_id == user.id)
    if note_id is not None:
        statement = statement.where(MiaJob.note_id == note_id)
    if status_filter is not None:
        statement = statement.where(MiaJob.status == status_filter)
    return [_job_response(job) for job in session.scalars(statement)]


@router.get("/{job_id}", response_model=MiaJobRead)
def get_job(job_id: str, session: SessionDep, user: NotesReadUser) -> MiaJobRead:
    job = session.scalars(
        select(MiaJob).where(MiaJob.id == job_id).options(joinedload(MiaJob.user))
    ).one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _ensure_can_read_job(job, user)
    return _job_response(job)
