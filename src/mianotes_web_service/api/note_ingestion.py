from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import AuthContextDep, NotesWriteUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Folder, Note, SourceFile, new_id
from mianotes_web_service.domain.schemas import (
    NoteCreateFromText,
    NoteCreateFromUrl,
    NoteIngestionRead,
    NoteRead,
)
from mianotes_web_service.services.jobs import create_job
from mianotes_web_service.services.auth_context import AuthContext
from mianotes_web_service.services.note_repository import read_note_for_response
from mianotes_web_service.services.note_responses import (
    note_ingestion_response,
    note_is_starred,
    note_response,
)
from mianotes_web_service.services.note_tags import sync_note_tags
from mianotes_web_service.services.parser_types import ParserError
from mianotes_web_service.services.parser_url import url_source_extension, validate_fetch_url
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.storage import (
    FilesystemStorage,
    infer_title,
    summarize_text,
)
from mianotes_web_service.services.upload_limits import UploadTooLargeError
from mianotes_web_service.services.workspace_context import WorkspaceContext

router = APIRouter(prefix="/notes", tags=["notes"])
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
    ".mp4",
    ".odt",
    ".pdf",
    ".png",
    ".rtf",
    ".tif",
    ".tiff",
    ".txt",
    ".wav",
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
    ".mp4": "audio",
    ".odt": "document",
    ".pdf": "pdf",
    ".png": "image",
    ".rtf": "document",
    ".tif": "image",
    ".tiff": "image",
    ".txt": "text",
    ".wav": "audio",
}


def _source_type_from_filename(filename: str) -> str:
    return SOURCE_TYPE_BY_EXTENSION.get(Path(filename).suffix.lower(), "file")


def _enqueue_job(
    request: Request,
    background_tasks: BackgroundTasks,
    job_id: str,
    session: Session,
) -> None:
    workspace = session.info.get("workspace")
    request.app.state.job_runner.enqueue(
        background_tasks,
        job_id,
        workspace if isinstance(workspace, WorkspaceContext) else None,
    )


def _ensure_notes_write(context: AuthContext):
    if context.is_browser_session or "admin" in context.scopes or "notes:write" in context.scopes:
        return context.user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="API token requires notes:write scope",
    )


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
    storage = FilesystemStorage(workspace_paths_for_session(session).data_dir)
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
    sync_note_tags(session, note, payload.tags)
    session.commit()
    return note_response(
        read_note_for_response(session, note.id),
        request,
        is_starred=note_is_starred(session, note.id, user.id),
        session=session,
    )


@router.post("/from-file", response_model=NoteIngestionRead, status_code=status.HTTP_201_CREATED)
def create_note_from_file(
    request: Request,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    context: AuthContextDep,
    folder_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
) -> NoteRead:
    user = _ensure_notes_write(context)
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
    storage = FilesystemStorage(workspace_paths_for_session(session).data_dir)
    try:
        paths = storage.write_uploaded_file_note(
            username=user.username,
            folder=folder.path,
            title=note_title,
            filename=note_id,
            original_filename=file.filename,
            source_stream=file.file,
            max_bytes=get_settings().max_upload_bytes,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File is too large. Maximum upload size is {exc.max_bytes} bytes.",
        ) from exc

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
        client=context.agent_client,
    )
    session.commit()
    session.refresh(job)
    _enqueue_job(request, background_tasks, job.id, session)
    return note_ingestion_response(
        read_note_for_response(session, note.id),
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
    context: AuthContextDep,
) -> NoteIngestionRead:
    user = _ensure_notes_write(context)
    folder = session.get(Folder, payload.folder_id)
    if folder is None or folder.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    url = str(payload.url)
    try:
        validate_fetch_url(url)
    except ParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    parsed_url = urlparse(url)
    title = payload.title or infer_title(parsed_url.path.rsplit("/", 1)[-1] or parsed_url.netloc)
    source_extension = url_source_extension(url) or ".html"
    note_id = new_id()
    storage = FilesystemStorage(workspace_paths_for_session(session).data_dir)
    paths = storage.write_url_note_placeholder(
        username=user.username,
        folder=folder.path,
        title=title,
        filename=note_id,
        url=url,
        source_extension=source_extension,
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
        content_type=mimetypes.types_map.get(source_extension, "application/octet-stream"),
    )
    session.add(source_file)
    session.flush()
    sync_note_tags(session, note, payload.tags)
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
        client=context.agent_client,
    )
    session.commit()
    session.refresh(job)
    _enqueue_job(request, background_tasks, job.id, session)
    return note_ingestion_response(
        read_note_for_response(session, note.id),
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
