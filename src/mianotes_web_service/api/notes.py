from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Comment, Note, SourceFile, Topic, User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import NoteCreateFromText, NoteListItem, NoteRead
from mianotes_web_service.services.storage import FilesystemStorage, infer_title, slugify

router = APIRouter(prefix="/notes", tags=["notes"])
SessionDep = Annotated[Session, Depends(get_session)]


def _read_note_or_404(session: Session, note_id: str) -> Note:
    statement = (
        select(Note)
        .where(Note.id == note_id)
        .options(joinedload(Note.user), joinedload(Note.topic), joinedload(Note.source_files))
    )
    note = session.scalars(statement).unique().one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


def _file_url(request: Request, path: str | Path) -> str:
    data_dir = get_settings().data_dir.resolve()
    target = Path(path).resolve()
    try:
        public_path = target.relative_to(data_dir)
    except ValueError:
        public_path = Path(path)
    return str(request.url_for("get_data_file", file_path=str(public_path)))


def _note_response(note: Note, request: Request) -> NoteRead:
    text = Path(note.note_path).read_text(encoding="utf-8")
    source_files = [
        {
            "id": source_file.id,
            "file_path": source_file.file_path,
            "original_filename": source_file.original_filename,
            "content_type": source_file.content_type,
            "url": _file_url(request, source_file.file_path),
        }
        for source_file in note.source_files
    ]
    comments_path = ""
    if note.comments:
        comments_path = note.comments[0].comments_path
    return NoteRead(
        id=note.id,
        user=note.user,
        topic=note.topic,
        created_at=note.created_at,
        updated_at=note.updated_at,
        title=note.title,
        text=text,
        note_url=_file_url(request, note.note_path),
        source_files=source_files,
        comments_url=_file_url(request, comments_path) if comments_path else "",
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
        },
    )


@router.post("/from-text", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note_from_text(
    payload: NoteCreateFromText,
    session: SessionDep,
    request: Request,
) -> NoteRead:
    user = session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    topic = session.get(Topic, payload.topic_id)
    if topic is None or topic.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    title = payload.title or infer_title(payload.text)
    storage = FilesystemStorage(get_settings().data_dir)
    paths = storage.write_text_note(
        username=user.username,
        topic=topic.slug,
        title=title,
        text=payload.text,
    )

    note = Note(user_id=user.id, topic_id=topic.id, title=title, note_path=str(paths.note_path))
    session.add(note)
    session.flush()
    if paths.source_path is not None:
        session.add(
            SourceFile(
                note_id=note.id,
                file_path=str(paths.source_path),
                original_filename=f"{slugify(title)}.source.txt",
                content_type="text/plain",
            )
        )
    session.add(Comment(note_id=note.id, comments_path=str(paths.comments_path)))
    session.commit()
    return _note_response(_read_note_or_404(session, note.id), request)


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteCreateFromText, session: SessionDep, request: Request) -> NoteRead:
    return create_note_from_text(payload, session, request)


@router.get("", response_model=list[NoteListItem])
def list_notes(
    session: SessionDep,
    user_id: Annotated[str | None, Query()] = None,
    topic_id: Annotated[str | None, Query()] = None,
) -> list[Note]:
    statement = select(Note).order_by(Note.created_at.desc())
    if user_id is not None:
        statement = statement.where(Note.user_id == user_id)
    if topic_id is not None:
        statement = statement.where(Note.topic_id == topic_id)
    return list(session.scalars(statement))


@router.get("/{note_id}", response_model=NoteRead)
def get_note(note_id: str, session: SessionDep, request: Request) -> NoteRead:
    return _note_response(_read_note_or_404(session, note_id), request)


@router.get("/{note_id}/comments")
def get_note_comments(note_id: str, session: SessionDep) -> dict[str, object]:
    note = _read_note_or_404(session, note_id)
    if not note.comments:
        return {"comments": []}
    return {"comments_path": note.comments[0].comments_path}
