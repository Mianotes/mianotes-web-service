from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.api.dependencies import (
    CommentsWriteUser,
    NotesReadUser,
    NotesWriteUser,
    ShareWriteUser,
    TagsWriteUser,
)
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Comment, Note, SourceFile, Tag, Topic, User, new_id
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import (
    MAX_TAGS_PER_NOTE,
    CommentCreate,
    CommentRead,
    CommentUpdate,
    NoteCreateFromText,
    NoteListItem,
    NoteRead,
    NoteUpdate,
    TagsUpdate,
)
from mianotes_web_service.services.share import (
    generate_share_token,
    get_share_secret,
    hash_share_token,
)
from mianotes_web_service.services.storage import (
    FilesystemStorage,
    infer_title,
    render_markdown_note,
    replace_markdown_title,
    slugify,
)

router = APIRouter(prefix="/notes", tags=["notes"])
SessionDep = Annotated[Session, Depends(get_session)]
SUPPORTED_UPLOAD_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".jpeg",
    ".jpg",
    ".md",
    ".markdown",
    ".odt",
    ".pdf",
    ".png",
    ".rtf",
    ".tif",
    ".tiff",
    ".txt",
}
SOURCE_TYPE_BY_EXTENSION = {
    ".csv": "spreadsheet",
    ".doc": "document",
    ".docx": "document",
    ".htm": "html",
    ".html": "html",
    ".jpeg": "image",
    ".jpg": "image",
    ".md": "markdown",
    ".markdown": "markdown",
    ".odt": "document",
    ".pdf": "pdf",
    ".png": "image",
    ".rtf": "document",
    ".tif": "image",
    ".tiff": "image",
    ".txt": "text",
}


def _read_note_or_404(session: Session, note_id: str) -> Note:
    statement = (
        select(Note)
        .where(Note.id == note_id)
        .options(
            joinedload(Note.user),
            joinedload(Note.topic),
            joinedload(Note.source_files),
            joinedload(Note.comments).joinedload(Comment.user),
            joinedload(Note.tags),
        )
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


def _share_url(request: Request, note: Note, token: str | None = None) -> str | None:
    if token:
        return str(request.url_for("get_shared_note", token=token))
    if note.shared_at is not None:
        return str(request.url_for("get_shared_note", token="<share-token>"))
    return None


def _note_response(note: Note, request: Request, share_token: str | None = None) -> NoteRead:
    text = Path(note.note_path).read_text(encoding="utf-8")
    source_files = [
        {
            "id": source_file.id,
            "file_path": source_file.file_path,
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
                else _file_url(request, source_file.file_path)
            ),
        }
        for source_file in note.source_files
    ]
    return NoteRead(
        id=note.id,
        user=note.user,
        topic=note.topic,
        created_at=note.created_at,
        updated_at=note.updated_at,
        title=note.title,
        status=note.status,
        source_type=note.source_type,
        revision_number=note.revision_number,
        is_published=note.is_published,
        published_at=note.published_at,
        shared_at=note.shared_at,
        text=text,
        note_url=_file_url(request, note.note_path),
        source_files=source_files,
        comments_count=len([comment for comment in note.comments if comment.body]),
        comments_url=str(request.url_for("get_note_comments", note_id=note.id)),
        tags=note.tags,
        share_url=_share_url(request, note, share_token),
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


def _source_type_from_filename(filename: str) -> str:
    return SOURCE_TYPE_BY_EXTENSION.get(Path(filename).suffix.lower(), "file")


def _sync_note_tags(session: Session, note: Note, tag_names: list[str]) -> None:
    normalized_names: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in tag_names:
        normalized = " ".join(name.strip().split())
        if not normalized:
            continue
        slug = slugify(normalized)
        if slug in seen:
            continue
        seen.add(slug)
        normalized_names.append((normalized, slug))

    if len(normalized_names) > MAX_TAGS_PER_NOTE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A note can have at most {MAX_TAGS_PER_NOTE} tags",
        )

    tags: list[Tag] = []
    for normalized, slug in normalized_names:
        tag = session.scalars(select(Tag).where(Tag.slug == slug)).one_or_none()
        if tag is None:
            tag = Tag(name=normalized, slug=slug)
            session.add(tag)
            session.flush()
        tags.append(tag)
    note.tags = tags


def _read_note_by_share_token(session: Session, token: str) -> Note:
    secret = get_share_secret(session)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared note not found")
    token_hash = hash_share_token(secret, token)
    statement = (
        select(Note)
        .where(Note.share_token_hash == token_hash, Note.shared_at.is_not(None))
        .options(
            joinedload(Note.user),
            joinedload(Note.topic),
            joinedload(Note.source_files),
            joinedload(Note.comments).joinedload(Comment.user),
            joinedload(Note.tags),
        )
    )
    note = session.scalars(statement).unique().one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared note not found")
    return note


def _ensure_can_change_note(note: Note, user: User) -> None:
    if user.is_admin or note.user_id == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cannot change this note",
    )


@router.post("/from-text", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note_from_text(
    payload: NoteCreateFromText,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
) -> NoteRead:
    topic = session.get(Topic, payload.topic_id)
    if topic is None or topic.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    title = payload.title or infer_title(payload.text)
    note_id = new_id()
    storage = FilesystemStorage(get_settings().data_dir)
    paths = storage.write_text_note(
        username=user.username,
        topic=topic.slug,
        title=title,
        text=payload.text,
        filename=note_id,
    )

    note = Note(
        id=note_id,
        user_id=user.id,
        topic_id=topic.id,
        title=title,
        source_type="text",
        note_path=str(paths.note_path),
    )
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
    _sync_note_tags(session, note, payload.tags)
    session.commit()
    return _note_response(_read_note_or_404(session, note.id), request)


@router.post("/from-file", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note_from_file(
    request: Request,
    session: SessionDep,
    user: NotesWriteUser,
    topic_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
) -> NoteRead:
    topic = session.get(Topic, topic_id)
    if topic is None or topic.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File required",
        )

    extension = Path(file.filename).suffix.lower()
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type",
        )

    note_id = new_id()
    note_title = title or infer_title(Path(file.filename).stem.replace("-", " ").replace("_", " "))
    storage = FilesystemStorage(get_settings().data_dir)
    paths = storage.write_uploaded_file_note(
        username=user.username,
        topic=topic.slug,
        title=note_title,
        filename=note_id,
        original_filename=file.filename,
        source_stream=file.file,
    )

    note = Note(
        id=note_id,
        user_id=user.id,
        topic_id=topic.id,
        title=note_title,
        status="pending_parse",
        source_type=_source_type_from_filename(file.filename),
        note_path=str(paths.note_path),
    )
    session.add(note)
    session.flush()
    if paths.source_path is not None:
        session.add(
            SourceFile(
                note_id=note.id,
                file_path=str(paths.source_path),
                original_filename=file.filename,
                content_type=file.content_type,
            )
        )
    session.commit()
    return _note_response(_read_note_or_404(session, note.id), request)


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreateFromText,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
) -> NoteRead:
    return create_note_from_text(payload, session, request, user)


@router.get("", response_model=list[NoteListItem])
def list_notes(
    session: SessionDep,
    user: NotesReadUser,
    user_id: Annotated[str | None, Query()] = None,
    topic_id: Annotated[str | None, Query()] = None,
) -> list[Note]:
    statement = select(Note).order_by(Note.created_at.desc())
    if user_id is not None:
        statement = statement.where(Note.user_id == user_id)
    if topic_id is not None:
        statement = statement.where(Note.topic_id == topic_id)
    return list(session.scalars(statement))


@router.get("/shared/{token}", response_model=NoteRead, name="get_shared_note")
def get_shared_note(token: str, session: SessionDep, request: Request) -> NoteRead:
    note = _read_note_by_share_token(session, token)
    return _note_response(note, request, share_token=token)


@router.get("/shared/{token}/files/{source_file_id}", name="get_shared_source_file")
def get_shared_source_file(
    token: str,
    source_file_id: str,
    session: SessionDep,
) -> FileResponse:
    note = _read_note_by_share_token(session, token)
    source_file = next(
        (candidate for candidate in note.source_files if candidate.id == source_file_id),
        None,
    )
    if source_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    target = Path(source_file.file_path)
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(target)


@router.get("/{note_id}", response_model=NoteRead)
def get_note(
    note_id: str,
    session: SessionDep,
    request: Request,
    user: NotesReadUser,
) -> NoteRead:
    return _note_response(_read_note_or_404(session, note_id), request)


@router.post("/{note_id}/share")
def create_note_share(
    note_id: str,
    session: SessionDep,
    request: Request,
    user: ShareWriteUser,
) -> dict[str, str]:
    note = _read_note_or_404(session, note_id)
    _ensure_can_change_note(note, user)
    secret = get_share_secret(session, create=True)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    token = generate_share_token()
    note.share_token_hash = hash_share_token(secret, token)
    note.shared_at = datetime.now(UTC)
    session.commit()
    return {"share_url": str(request.url_for("get_shared_note", token=token))}


@router.delete("/{note_id}/share", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_share(note_id: str, session: SessionDep, user: ShareWriteUser) -> None:
    note = _read_note_or_404(session, note_id)
    _ensure_can_change_note(note, user)
    note.share_token_hash = None
    note.shared_at = None
    session.commit()


@router.put("/{note_id}/tags", response_model=NoteRead)
def update_note_tags(
    note_id: str,
    payload: TagsUpdate,
    session: SessionDep,
    request: Request,
    user: TagsWriteUser,
) -> NoteRead:
    note = _read_note_or_404(session, note_id)
    _ensure_can_change_note(note, user)
    _sync_note_tags(session, note, payload.tags)
    session.commit()
    return _note_response(_read_note_or_404(session, note.id), request)


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    note_id: str,
    payload: NoteUpdate,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
) -> NoteRead:
    note = _read_note_or_404(session, note_id)
    _ensure_can_change_note(note, user)

    next_title = payload.title or note.title
    note_path = Path(note.note_path)
    if payload.text is not None:
        note_path.write_text(
            render_markdown_note(title=next_title, text=payload.text),
            encoding="utf-8",
        )
        note.revision_number += 1
    elif payload.title is not None:
        note_path.write_text(
            replace_markdown_title(note_path.read_text(encoding="utf-8"), next_title),
            encoding="utf-8",
        )
        note.revision_number += 1
    note.title = next_title
    if payload.is_published is not None:
        note.is_published = payload.is_published
        note.published_at = datetime.now(UTC) if payload.is_published else None
    if payload.tags is not None:
        _sync_note_tags(session, note, payload.tags)
    session.commit()
    return _note_response(_read_note_or_404(session, note.id), request)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, session: SessionDep, user: NotesWriteUser) -> None:
    note = _read_note_or_404(session, note_id)
    _ensure_can_change_note(note, user)
    paths = [Path(note.note_path)]
    paths.extend(Path(source.file_path) for source in note.source_files)
    paths.extend(Path(comment.comments_path) for comment in note.comments if comment.comments_path)
    session.delete(note)
    session.commit()
    for path in paths:
        path.unlink(missing_ok=True)


@router.get("/{note_id}/comments")
def get_note_comments(
    note_id: str,
    session: SessionDep,
    user: NotesReadUser,
) -> list[CommentRead]:
    note = _read_note_or_404(session, note_id)
    return [
        CommentRead.model_validate(comment)
        for comment in sorted(note.comments, key=lambda item: item.created_at)
        if comment.body
    ]


@router.post("/{note_id}/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
def create_note_comment(
    note_id: str,
    payload: CommentCreate,
    session: SessionDep,
    user: CommentsWriteUser,
) -> Comment:
    note = _read_note_or_404(session, note_id)
    comment = Comment(note_id=note.id, user_id=user.id, body=payload.body, comments_path="")
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return comment


@router.patch("/{note_id}/comments/{comment_id}", response_model=CommentRead)
def update_note_comment(
    note_id: str,
    comment_id: str,
    payload: CommentUpdate,
    session: SessionDep,
    user: CommentsWriteUser,
) -> Comment:
    _read_note_or_404(session, note_id)
    comment = session.get(Comment, comment_id)
    if comment is None or comment.note_id != note_id or not comment.body:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if not user.is_admin and comment.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change this comment",
        )
    comment.body = payload.body
    session.commit()
    session.refresh(comment)
    return comment


@router.delete("/{note_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_comment(
    note_id: str,
    comment_id: str,
    session: SessionDep,
    user: CommentsWriteUser,
) -> None:
    _read_note_or_404(session, note_id)
    comment = session.get(Comment, comment_id)
    if comment is None or comment.note_id != note_id or not comment.body:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if not user.is_admin and comment.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change this comment",
        )
    session.delete(comment)
    session.commit()
