from __future__ import annotations

import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.api.dependencies import (
    CommentsWriteUser,
    NotesReadUser,
    NotesWriteUser,
    ShareWriteUser,
    TagsWriteUser,
)
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import (
    Comment,
    Folder,
    Note,
    NoteStar,
    SourceFile,
    Tag,
    User,
    new_id,
)
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import (
    MAX_TAGS_PER_NOTE,
    CommentCreate,
    CommentRead,
    CommentUpdate,
    MiaJobRead,
    MiaPromptRead,
    NoteCreateFromText,
    NoteCreateFromUrl,
    NoteIngestionRead,
    NoteListItem,
    NoteRead,
    NoteStarUpdate,
    NoteUpdate,
    TagsUpdate,
)
from mianotes_web_service.services.jobs import create_job, decode_job_payload
from mianotes_web_service.services.mia import MiaUnavailable, prompt_markdown
from mianotes_web_service.services.paths import (
    folder_directory,
    note_file_path,
    note_image_directory,
    source_file_path,
)
from mianotes_web_service.services.share import (
    generate_share_token,
    get_share_secret,
    hash_share_token,
)
from mianotes_web_service.services.storage import (
    FilesystemStorage,
    infer_title,
    markdown_note_body,
    render_markdown_note,
    replace_markdown_title,
    slugify,
    summarize_markdown_note,
    summarize_text,
)

router = APIRouter(prefix="/notes", tags=["notes"])
SessionDep = Annotated[Session, Depends(get_session)]
MISSING_NOTE_FILE_DETAIL = (
    "This note still exists in the database, but its Markdown file no longer exists "
    "in the filesystem. It may have been deleted or moved outside Mianotes."
)
SUPPORTED_UPLOAD_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".md",
    ".markdown",
    ".mp3",
    ".odt",
    ".pdf",
    ".png",
    ".rtf",
    ".tif",
    ".tiff",
    ".txt",
    ".wav",
}
SUPPORTED_EDITOR_IMAGE_EXTENSIONS = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
}
EDITOR_IMAGE_EXTENSION_BY_CONTENT_TYPE = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
SOURCE_TYPE_BY_EXTENSION = {
    ".csv": "spreadsheet",
    ".doc": "document",
    ".docx": "document",
    ".htm": "html",
    ".html": "html",
    ".jpeg": "image",
    ".jpg": "image",
    ".m4a": "audio",
    ".md": "markdown",
    ".markdown": "markdown",
    ".mp3": "audio",
    ".odt": "document",
    ".pdf": "pdf",
    ".png": "image",
    ".rtf": "document",
    ".tif": "image",
    ".tiff": "image",
    ".txt": "text",
    ".wav": "audio",
}


def _read_note_or_404(session: Session, note_id: str) -> Note:
    statement = (
        select(Note)
        .where(Note.id == note_id)
        .options(
            joinedload(Note.user),
            joinedload(Note.folder),
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
    return str(request.url_for("get_folder_file", file_path=str(public_path)))


def _share_url(request: Request, note: Note, token: str | None = None) -> str | None:
    if token:
        return str(request.url_for("get_shared_note", token=token))
    if note.shared_at is not None:
        return str(request.url_for("get_shared_note", token="<share-token>"))
    return None


def _note_is_starred(session: Session, note_id: str, user_id: str) -> bool:
    return session.scalars(
        select(NoteStar.note_id).where(
            NoteStar.note_id == note_id,
            NoteStar.user_id == user_id,
        )
    ).first() is not None


def _starred_note_ids(session: Session, note_ids: list[str], user_id: str) -> set[str]:
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


def _note_response(
    note: Note,
    request: Request,
    *,
    is_starred: bool = False,
    share_token: str | None = None,
) -> NoteRead:
    note_path = note_file_path(note)
    try:
        text = note_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MISSING_NOTE_FILE_DETAIL,
        ) from exc
    source_files = [
        {
            "id": source_file.id,
            "file_path": str(source_file_path(source_file)),
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
                else _file_url(request, source_file_path(source_file))
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
        note_url=_file_url(request, note_path),
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
            "star": {
                "method": "PATCH",
                "url": str(request.url_for("update_note_star", note_id=note.id)),
            },
        },
    )


def _normalized_summary(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _note_summary_needs_refresh(note: Note) -> bool:
    summary = _normalized_summary(note.summary)
    title = _normalized_summary(note.title)
    if not summary or summary == title:
        return True
    return bool(title and summary.startswith(f"{title} created:"))


def _source_file_list_payload(note: Note, request: Request) -> list[dict[str, object]]:
    return [
        {
            "id": source_file.id,
            "file_path": str(source_file_path(source_file)),
            "original_filename": source_file.original_filename,
            "content_type": source_file.content_type,
            "url": _file_url(request, source_file_path(source_file)),
        }
        for source_file in note.source_files
    ]


def _note_list_response(note: Note, request: Request, *, is_starred: bool = False) -> NoteListItem:
    if _note_summary_needs_refresh(note):
        try:
            note.summary = summarize_markdown_note(note_file_path(note).read_text(encoding="utf-8"))
        except OSError:
            note.summary = ""
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
        note_path=str(note_file_path(note)),
        source_files=_source_file_list_payload(note, request),
        created_at=note.created_at,
        updated_at=note.updated_at,
        comments_count=len([comment for comment in note.comments if comment.body]),
        tags=note.tags,
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
            joinedload(Note.folder),
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
    owner_name = note.user.name if note.user is not None else "the note owner"
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Only {owner_name} or an admin can change this note.",
    )


def _mia_prompt(body: str) -> str | None:
    stripped = body.strip()
    if not stripped.lower().startswith("@mia"):
        return None
    prompt = stripped[4:].strip()
    if not prompt:
        raise HTTPException(
            status_code=422,
            detail="Mia prompt cannot be empty",
        )
    return prompt


def _mia_job_response(job) -> MiaJobRead:
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


def _note_ingestion_response(
    note: Note,
    job,
    request: Request,
    user: User,
    session: Session,
) -> NoteIngestionRead:
    note_read = _note_response(
        note,
        request,
        is_starred=_note_is_starred(session, note.id, user.id),
    )
    return NoteIngestionRead(
        **note_read.model_dump(),
        note_id=note.id,
        job_id=job.id,
        job_status=job.status,
        note_api_url=str(request.url_for("get_note", note_id=note.id)),
        job_api_url=str(request.url_for("get_job", job_id=job.id)),
        job=_mia_job_response(job),
    )


def _enqueue_job(request: Request, background_tasks: BackgroundTasks, job_id: str) -> None:
    request.app.state.job_runner.enqueue(background_tasks, job_id)


def _validate_stored_moves(moves: list[tuple[Path, Path]]) -> None:
    for current_path, target_path in moves:
        if current_path.resolve() == target_path.resolve():
            continue
        if not current_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note file not found",
            )
        if target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A file already exists in the target folder",
            )


def _move_stored_path(current_path: Path, target_path: Path) -> None:
    if current_path.resolve() == target_path.resolve():
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(current_path), str(target_path))


def _move_note_to_folder(note: Note, target_folder: Folder) -> None:
    if note.folder_id == target_folder.id:
        return

    current_folder = note.folder
    current_folder_dir = folder_directory(current_folder) if current_folder else None
    target_folder_dir = folder_directory(target_folder)
    FilesystemStorage(get_settings().data_dir).prepare_folder_directory(target_folder_dir)

    current_note_path = note_file_path(note)
    note_filename = note.filename or current_note_path.name
    target_note_path = target_folder_dir / note_filename
    source_moves: list[tuple[SourceFile, Path, Path, str]] = []

    for source_file in note.source_files:
        current_source_path = source_file_path(source_file)
        source_filename = source_file.filename
        if not source_filename and current_folder_dir is not None:
            try:
                source_filename = current_source_path.relative_to(current_folder_dir).as_posix()
            except ValueError:
                source_filename = None
        if not source_filename:
            continue
        source_moves.append(
            (
                source_file,
                current_source_path,
                target_folder_dir / source_filename,
                source_filename,
            )
        )

    current_image_dir = note_image_directory(note)
    target_image_dir = target_folder_dir / "images" / note.id[:8]

    path_moves = [
        (current_note_path, target_note_path),
        *[
            (current_source_path, target_source_path)
            for _, current_source_path, target_source_path, _ in source_moves
        ],
    ]
    if current_image_dir.exists():
        path_moves.append((current_image_dir, target_image_dir))
    _validate_stored_moves(path_moves)

    _move_stored_path(current_note_path, target_note_path)
    for source_file, current_source_path, target_source_path, source_filename in source_moves:
        _move_stored_path(current_source_path, target_source_path)
        source_file.filename = source_filename
        source_file.file_path = str(target_source_path)
    if current_image_dir.exists():
        _move_stored_path(current_image_dir, target_image_dir)

    note.folder_id = target_folder.id
    note.folder = target_folder
    note.filename = note_filename
    note.note_path = str(target_note_path)


@router.post("/from-text", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note_from_text(
    payload: NoteCreateFromText,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
) -> NoteRead:
    folder = session.get(Folder, payload.folder_id)
    if folder is None or folder.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    title = payload.title or infer_title(payload.text)
    note_id = new_id()
    storage = FilesystemStorage(get_settings().data_dir)
    paths = storage.write_text_note(
        username=user.username,
        folder=folder.path,
        title=title,
        text=payload.text,
        filename=note_id,
    )

    note = Note(
        id=note_id,
        user_id=user.id,
        folder_id=folder.id,
        title=title,
        source_type="text",
        summary=summarize_text(payload.text),
        filename=paths.note_path.name,
        note_path=str(paths.note_path),
    )
    session.add(note)
    session.flush()
    if paths.source_path is not None:
        session.add(
            SourceFile(
                note_id=note.id,
                filename=str(paths.source_path.relative_to(paths.directory)),
                file_path=str(paths.source_path),
                original_filename="original.txt",
                content_type="text/plain",
            )
        )
    _sync_note_tags(session, note, payload.tags)
    session.commit()
    return _note_response(
        _read_note_or_404(session, note.id),
        request,
        is_starred=_note_is_starred(session, note.id, user.id),
    )


@router.post("/from-file", response_model=NoteIngestionRead, status_code=status.HTTP_201_CREATED)
def create_note_from_file(
    request: Request,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    user: NotesWriteUser,
    folder_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
) -> NoteRead:
    folder = session.get(Folder, folder_id)
    if folder is None or folder.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
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
    note_title = title.strip()
    if not note_title:
        raise HTTPException(
            status_code=422,
            detail="Title required",
        )
    storage = FilesystemStorage(get_settings().data_dir)
    paths = storage.write_uploaded_file_note(
        username=user.username,
        folder=folder.path,
        title=note_title,
        filename=note_id,
        original_filename=file.filename,
        source_stream=file.file,
    )

    note = Note(
        id=note_id,
        user_id=user.id,
        folder_id=folder.id,
        title=note_title,
        status="pending_parse",
        source_type=_source_type_from_filename(file.filename),
        summary=(
            "Your file has been added to the queue. Mia will read it and turn it into "
            "a note as soon as possible."
        ),
        filename=paths.note_path.name,
        note_path=str(paths.note_path),
    )
    session.add(note)
    session.flush()
    source_file = None
    if paths.source_path is not None:
        source_file = SourceFile(
            note_id=note.id,
            filename=str(paths.source_path.relative_to(paths.directory)),
            file_path=str(paths.source_path),
            original_filename=file.filename,
            content_type=file.content_type,
        )
        session.add(source_file)
        session.flush()
    if source_file is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    job = create_job(
        session,
        user,
        job_type="parse_file",
        note_id=note.id,
        input_payload={
            "note_id": note.id,
            "source_file_id": source_file.id,
            "operation": "parse_file",
        },
    )
    session.commit()
    session.refresh(job)
    _enqueue_job(request, background_tasks, job.id)
    return _note_ingestion_response(
        _read_note_or_404(session, note.id),
        job,
        request,
        user,
        session,
    )


@router.post("/from-url", response_model=NoteIngestionRead, status_code=status.HTTP_201_CREATED)
def create_note_from_url(
    payload: NoteCreateFromUrl,
    request: Request,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    user: NotesWriteUser,
) -> NoteIngestionRead:
    folder = session.get(Folder, payload.folder_id)
    if folder is None or folder.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    url = str(payload.url)
    parsed_url = urlparse(url)
    title = payload.title or infer_title(parsed_url.path.rsplit("/", 1)[-1] or parsed_url.netloc)
    note_id = new_id()
    storage = FilesystemStorage(get_settings().data_dir)
    paths = storage.write_url_note_placeholder(
        username=user.username,
        folder=folder.path,
        title=title,
        filename=note_id,
        url=url,
    )
    if paths.source_path is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    note = Note(
        id=note_id,
        user_id=user.id,
        folder_id=folder.id,
        title=title,
        status="pending_parse",
        source_type="link",
        summary="Mia is indexing this link.",
        filename=paths.note_path.name,
        note_path=str(paths.note_path),
    )
    session.add(note)
    session.flush()
    source_file = SourceFile(
        note_id=note.id,
        filename=str(paths.source_path.relative_to(paths.directory)),
        file_path=str(paths.source_path),
        original_filename=url[:500],
        content_type="text/html",
    )
    session.add(source_file)
    session.flush()
    _sync_note_tags(session, note, payload.tags)
    job = create_job(
        session,
        user,
        job_type="parse_url",
        note_id=note.id,
        input_payload={
            "note_id": note.id,
            "source_file_id": source_file.id,
            "operation": "parse_url",
            "url": url,
        },
    )
    session.commit()
    session.refresh(job)
    _enqueue_job(request, background_tasks, job.id)
    return _note_ingestion_response(
        _read_note_or_404(session, note.id),
        job,
        request,
        user,
        session,
    )


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreateFromText,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
) -> NoteRead:
    return create_note_from_text(payload, session, request, user)


@router.post("/{note_id}/images", status_code=status.HTTP_201_CREATED)
def upload_note_image(
    note_id: str,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
    image: Annotated[UploadFile, File()],
) -> dict[str, str]:
    note = _read_note_or_404(session, note_id)
    _ensure_can_change_note(note, user)
    if not image.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Image required",
        )

    content_type = (image.content_type or "").split(";", 1)[0].strip().lower()
    extension = Path(image.filename).suffix.lower()
    if extension == ".jpeg":
        extension = ".jpg"
    if extension not in SUPPORTED_EDITOR_IMAGE_EXTENSIONS:
        extension = EDITOR_IMAGE_EXTENSION_BY_CONTENT_TYPE.get(content_type, extension)
    if extension not in SUPPORTED_EDITOR_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image type",
        )

    directory = note_image_directory(note)
    directory.mkdir(parents=True, exist_ok=True)
    stem = slugify(Path(image.filename).stem, "image")[:80]
    target = directory / f"{stem}-{secrets.token_hex(4)}{extension}"
    with target.open("wb") as output:
        shutil.copyfileobj(image.file, output)
    return {"url": _file_url(request, target)}


@router.get("", response_model=list[NoteListItem])
def list_notes(
    session: SessionDep,
    request: Request,
    user: NotesReadUser,
    user_id: Annotated[str | None, Query()] = None,
    folder_id: Annotated[str | None, Query()] = None,
    starred: Annotated[bool | None, Query()] = None,
) -> list[NoteListItem]:
    statement = (
        select(Note)
        .options(
            joinedload(Note.comments),
            joinedload(Note.folder),
            joinedload(Note.source_files),
            joinedload(Note.tags),
        )
        .order_by(Note.created_at.desc())
    )
    if user_id is not None:
        statement = statement.where(Note.user_id == user_id)
    if folder_id is not None:
        statement = statement.where(Note.folder_id == folder_id)
    star_exists = exists().where(NoteStar.note_id == Note.id, NoteStar.user_id == user.id)
    if starred is True:
        statement = statement.where(star_exists)
    elif starred is False:
        statement = statement.where(~star_exists)
    notes = list(session.scalars(statement).unique())
    needs_summary_backfill = any(_note_summary_needs_refresh(note) for note in notes)
    starred_ids = _starred_note_ids(session, [note.id for note in notes], user.id)
    items = [
        _note_list_response(note, request, is_starred=note.id in starred_ids) for note in notes
    ]
    if needs_summary_backfill:
        session.commit()
    return items


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
    target = source_file_path(source_file)
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
    return _note_response(
        _read_note_or_404(session, note_id),
        request,
        is_starred=_note_is_starred(session, note_id, user.id),
    )


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
    return _note_response(
        _read_note_or_404(session, note.id),
        request,
        is_starred=_note_is_starred(session, note.id, user.id),
    )


@router.patch("/{note_id}/star", response_model=NoteRead, name="update_note_star")
def update_note_star(
    note_id: str,
    payload: NoteStarUpdate,
    session: SessionDep,
    request: Request,
    user: NotesWriteUser,
) -> NoteRead:
    note = _read_note_or_404(session, note_id)
    existing_star = session.scalars(
        select(NoteStar).where(NoteStar.note_id == note.id, NoteStar.user_id == user.id)
    ).one_or_none()
    if payload.is_starred and existing_star is None:
        session.add(NoteStar(note_id=note.id, user_id=user.id))
    elif not payload.is_starred and existing_star is not None:
        session.execute(
            delete(NoteStar).where(NoteStar.note_id == note.id, NoteStar.user_id == user.id)
        )
    session.commit()
    return _note_response(
        _read_note_or_404(session, note.id),
        request,
        is_starred=payload.is_starred,
    )


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

    if payload.folder_id is not None:
        folder = session.get(Folder, payload.folder_id)
        if folder is None or folder.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        _move_note_to_folder(note, folder)

    next_title = payload.title or note.title
    note_path = note_file_path(note)
    if payload.text is not None:
        note_path.write_text(
            render_markdown_note(title=next_title, text=payload.text),
            encoding="utf-8",
        )
        note.summary = summarize_text(payload.text)
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
    return _note_response(
        _read_note_or_404(session, note.id),
        request,
        is_starred=_note_is_starred(session, note.id, user.id),
    )


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, session: SessionDep, user: NotesWriteUser) -> None:
    note = _read_note_or_404(session, note_id)
    _ensure_can_change_note(note, user)
    paths = [note_file_path(note)]
    source_paths = [source_file_path(source) for source in note.source_files]
    paths.extend(source_paths)
    source_dirs = {path.parent for path in source_paths}
    image_dir = note_image_directory(note)
    session.delete(note)
    session.commit()
    for path in paths:
        path.unlink(missing_ok=True)
    shutil.rmtree(image_dir, ignore_errors=True)
    for source_dir in sorted(source_dirs, key=lambda path: len(path.parts), reverse=True):
        try:
            source_dir.rmdir()
        except OSError:
            pass


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


@router.post(
    "/{note_id}/comments",
    response_model=CommentRead | MiaPromptRead,
    status_code=status.HTTP_201_CREATED,
)
def create_note_comment(
    note_id: str,
    payload: CommentCreate,
    response: Response,
    session: SessionDep,
    user: CommentsWriteUser,
) -> Comment | MiaPromptRead:
    note = _read_note_or_404(session, note_id)
    prompt = _mia_prompt(payload.body)
    if prompt is not None:
        try:
            raw_markdown = (
                payload.markdown
                if payload.markdown is not None
                else note_file_path(note).read_text(encoding="utf-8")
            )
            result = prompt_markdown(
                title=note.title,
                markdown=markdown_note_body(raw_markdown) or raw_markdown,
                prompt=prompt,
            )
        except MiaUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # pragma: no cover - provider/network boundary
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Mia prompt failed",
            ) from exc
        response.status_code = status.HTTP_200_OK
        return MiaPromptRead(
            prompt=prompt,
            note_id=note.id,
            text=result.text,
        )

    response.status_code = status.HTTP_201_CREATED
    comment = Comment(note_id=note.id, user_id=user.id, body=payload.body)
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
