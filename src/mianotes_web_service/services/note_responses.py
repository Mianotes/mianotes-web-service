from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Note, NoteStar, User
from mianotes_web_service.domain.schemas import (
    AgentClientRead,
    MiaJobRead,
    NoteIngestionRead,
    NoteListItem,
    NoteRead,
)
from mianotes_web_service.services.jobs import decode_job_log, decode_job_payload
from mianotes_web_service.services.parsing import normalise_parsed_markdown
from mianotes_web_service.services.paths import note_file_path, source_file_path
from mianotes_web_service.services.storage import summarize_markdown_note
from mianotes_web_service.services.workspace_context import current_data_dir, session_data_dir

MISSING_NOTE_FILE_DETAIL = (
    "This note still exists in the database, but its Markdown file no longer exists "
    "in the filesystem. It may have been deleted or moved outside Mianotes."
)


def file_url(request: Request, path: str | Path, data_dir: Path | None = None) -> str:
    data_dir = (data_dir or current_data_dir(get_settings().data_dir)).resolve()
    target = Path(path).resolve()
    try:
        public_path = target.relative_to(data_dir)
    except ValueError:
        public_path = Path(path)
    return f"/{public_path.as_posix().lstrip('/')}"


def share_url(request: Request, note: Note, token: str | None = None) -> str | None:
    if token:
        return str(request.url_for("get_shared_note", token=token))
    if note.shared_at is not None:
        return str(request.url_for("get_shared_note", token="<share-token>"))
    return None


def note_is_starred(session: Session, note_id: str, user_id: str) -> bool:
    return session.scalars(
        select(NoteStar.note_id).where(
            NoteStar.note_id == note_id,
            NoteStar.user_id == user_id,
        )
    ).first() is not None


def starred_note_ids(session: Session, note_ids: list[str], user_id: str) -> set[str]:
    if not note_ids:
        return set()
    return set(
        session.scalars(
            select(NoteStar.note_id).where(
                NoteStar.user_id == user_id,
                NoteStar.note_id.in_(note_ids),
            )
        )
    )


def latest_note_job(note: Note):
    return max(note.jobs, key=lambda job: job.created_at, default=None)


def note_response(
    note: Note,
    request: Request,
    *,
    is_starred: bool = False,
    share_token: str | None = None,
    session: Session | None = None,
) -> NoteRead:
    data_dir = session_data_dir(session, get_settings().data_dir) if session is not None else None
    note_path = note_file_path(note, data_dir)
    try:
        text = note_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MISSING_NOTE_FILE_DETAIL,
        ) from exc
    normalized_text = normalise_parsed_markdown(text)
    if normalized_text != text:
        note_path.write_text(normalized_text, encoding="utf-8")
        text = normalized_text
    latest_job = latest_note_job(note)
    source_files = [
        {
            "id": source_file.id,
            "file_path": str(source_file_path(source_file, data_dir)),
            "original_filename": source_file.original_filename,
            "content_type": source_file.content_type,
            "url": (
                str(
                    request.url_for(
                        "get_shared_source_file",
                        token=share_token,
                        source_file_id=source_file.id,
                    )
                )
                if share_token
                else file_url(request, source_file_path(source_file, data_dir), data_dir)
            ),
        }
        for source_file in note.source_files
    ]
    return NoteRead(
        id=note.id,
        user=note.user,
        folder_id=note.folder_id,
        folder=note.folder,
        created_at=note.created_at,
        updated_at=note.updated_at,
        title=note.title,
        status=note.status,
        source_type=note.source_type,
        revision_number=note.revision_number,
        is_published=note.is_published,
        is_starred=is_starred,
        published_at=note.published_at,
        summary=note.summary,
        shared_at=note.shared_at,
        text=text,
        note_url=file_url(request, note_path, data_dir),
        source_files=source_files,
        comments_count=len([comment for comment in note.comments if comment.body]),
        comments_url=str(request.url_for("get_note_comments", note_id=note.id)),
        tags=note.tags,
        share_url=share_url(request, note, share_token),
        job_id=latest_job.id if latest_job is not None else None,
        job_status=latest_job.status if latest_job is not None else None,
        actions={
            "self": {"method": "GET", "url": str(request.url_for("get_note", note_id=note.id))},
            "update": {"method": "PATCH", "url": str(request.url_for("get_note", note_id=note.id))},
            "delete": {
                "method": "DELETE",
                "url": str(request.url_for("get_note", note_id=note.id)),
            },
            "comments": {
                "method": "GET",
                "url": str(request.url_for("get_note_comments", note_id=note.id)),
            },
            "star": {
                "method": "PATCH",
                "url": str(request.url_for("update_note_star", note_id=note.id)),
            },
        },
    )


def normalized_summary(value: str) -> str:
    return " ".join(value.strip().lower().split())


def note_summary_needs_refresh(note: Note) -> bool:
    summary = normalized_summary(note.summary)
    title = normalized_summary(note.title)
    if not summary or summary == title:
        return True
    return bool(title and summary.startswith(f"{title} created:"))


def source_file_list_payload(
    note: Note,
    request: Request,
    data_dir: Path | None = None,
) -> list[dict[str, object]]:
    return [
        {
            "id": source_file.id,
            "file_path": str(source_file_path(source_file, data_dir)),
            "original_filename": source_file.original_filename,
            "content_type": source_file.content_type,
            "url": file_url(request, source_file_path(source_file, data_dir), data_dir),
        }
        for source_file in note.source_files
    ]


def note_list_response(
    note: Note,
    request: Request,
    *,
    is_starred: bool = False,
    session: Session | None = None,
) -> NoteListItem:
    data_dir = session_data_dir(session, get_settings().data_dir) if session is not None else None
    if note_summary_needs_refresh(note):
        try:
            note.summary = summarize_markdown_note(
                note_file_path(note, data_dir).read_text(encoding="utf-8")
            )
        except OSError:
            note.summary = ""
    latest_job = latest_note_job(note)
    return NoteListItem(
        id=note.id,
        user_id=note.user_id,
        folder_id=note.folder_id,
        title=note.title,
        status=note.status,
        source_type=note.source_type,
        revision_number=note.revision_number,
        is_published=note.is_published,
        is_starred=is_starred,
        summary=note.summary,
        filename=note.filename,
        note_path=str(note_file_path(note, data_dir)),
        source_files=source_file_list_payload(note, request, data_dir),
        created_at=note.created_at,
        updated_at=note.updated_at,
        comments_count=len([comment for comment in note.comments if comment.body]),
        tags=note.tags,
        job_id=latest_job.id if latest_job is not None else None,
        job_status=latest_job.status if latest_job is not None else None,
    )


def mia_job_response(job) -> MiaJobRead:
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


def note_ingestion_response(
    note: Note,
    job,
    request: Request,
    user: User,
    session: Session,
) -> NoteIngestionRead:
    note_read = note_response(
        note,
        request,
        is_starred=note_is_starred(session, note.id, user.id),
        session=session,
    )
    return NoteIngestionRead(
        **note_read.model_dump(exclude={"job_id", "job_status"}),
        note_id=note.id,
        job_id=job.id,
        job_status=job.status,
        note_api_url=str(request.url_for("get_note", note_id=note.id)),
        job_api_url=str(request.url_for("get_job", job_id=job.id)),
        job=mia_job_response(job),
    )
