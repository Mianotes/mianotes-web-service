from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mianotes_web_service.api.dependencies import NotesReadUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Note, SourceFile
from mianotes_web_service.services.auth import (
    SESSION_COOKIE_NAME,
    decode_api_token_scopes,
    read_api_token,
    read_session_user,
    sync_instance_api_token_public_key,
    verify_instance_api_token,
)
from mianotes_web_service.services.paths import note_file_path, source_file_path

router = APIRouter(tags=["files"])
PRIVATE_DATA_FILENAMES = {"mia.db", "mia.db-wal", "mia.db-shm", "mia.db-journal"}


def _file_response(file_path: str) -> FileResponse:
    data_dir = get_settings().data_dir.resolve()
    target = (data_dir / file_path).resolve()
    if data_dir not in target.parents and target != data_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if target.name in PRIVATE_DATA_FILENAMES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(target)


def _clean_file_path(file_path: str) -> str:
    clean = file_path.strip("/")
    if not clean:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return clean


def _read_bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _has_authenticated_file_access(request: Request, session: Session) -> bool:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if read_session_user(session, session_token) is not None:
        return True

    raw_api_token = _read_bearer_token(request.headers.get("authorization"))
    if raw_api_token is None:
        return False

    api_token = read_api_token(session, raw_api_token)
    if api_token is not None:
        scopes = set(decode_api_token_scopes(api_token.scopes))
        return "admin" in scopes or "notes:read" in scopes

    settings = get_settings()
    if settings.api_token:
        sync_instance_api_token_public_key(session, settings.api_token)
        return verify_instance_api_token(session, raw_api_token)

    return False


def _published_markdown_response(file_path: str, session: Session) -> FileResponse:
    if file_path.startswith("sources/") or "/sources/" in file_path:
        return _published_source_response(file_path, session)

    data_dir = get_settings().data_dir.resolve()
    target = (data_dir / "markdown" / file_path).resolve()
    if data_dir not in target.parents and target != data_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    notes = session.scalars(
        select(Note).options(selectinload(Note.folder)).where(Note.is_published.is_(True))
    ).all()
    for note in notes:
        if note_file_path(note).resolve() == target:
            return _file_response(f"markdown/{file_path}")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


def _published_source_response(file_path: str, session: Session) -> FileResponse:
    data_dir = get_settings().data_dir.resolve()
    target = (data_dir / "markdown" / file_path).resolve()
    if data_dir not in target.parents and target != data_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    source_files = session.scalars(
        select(SourceFile)
        .join(SourceFile.note)
        .options(selectinload(SourceFile.note).selectinload(Note.folder))
        .where(Note.is_published.is_(True))
    ).all()
    for source_file in source_files:
        if source_file_path(source_file).resolve() == target:
            return _file_response(f"markdown/{file_path}")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.get("/html", include_in_schema=False)
@router.get("/html/", include_in_schema=False)
def get_published_html_root() -> FileResponse:
    return _file_response("html/index.html")


@router.get("/html/{file_path:path}", include_in_schema=False)
def get_published_html_file(file_path: str) -> FileResponse:
    return _file_response(f"html/{_clean_file_path(file_path)}")


@router.get("/markdown", include_in_schema=False)
@router.get("/markdown/", include_in_schema=False)
def get_markdown_root() -> FileResponse:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.get("/markdown/{file_path:path}", include_in_schema=False)
def get_markdown_file(
    file_path: str,
    request: Request,
    session: SessionDep,
) -> FileResponse:
    clean = _clean_file_path(file_path)
    if _has_authenticated_file_access(request, session):
        return _file_response(f"markdown/{clean}")
    return _published_markdown_response(clean, session)


@router.get("/{file_path:path}", name="get_folder_file")
def get_folder_file(file_path: str, user: NotesReadUser) -> FileResponse:
    return _file_response(file_path)
