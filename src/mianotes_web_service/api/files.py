from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mianotes_web_service.api.dependencies import (
    NotesReadUser,
    SessionDep,
    auth_context_from_bearer_token,
)
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Note, SourceFile
from mianotes_web_service.db.workspace_routing import workspace_by_id
from mianotes_web_service.services.auth import SESSION_COOKIE_NAME, read_session_user
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.storage_settings import (
    DATABASE_FILENAME,
    SQLITE_SIDECAR_SUFFIXES,
    SYSTEM_DATABASE_FILENAME,
)
from mianotes_web_service.services.workspace_context import current_data_dir

router = APIRouter(tags=["files"])
PRIVATE_DATA_FILENAMES = {
    DATABASE_FILENAME,
    SYSTEM_DATABASE_FILENAME,
    *(f"{DATABASE_FILENAME}{suffix}" for suffix in SQLITE_SIDECAR_SUFFIXES),
    *(f"{SYSTEM_DATABASE_FILENAME}{suffix}" for suffix in SQLITE_SIDECAR_SUFFIXES),
}


def _file_response(
    file_path: str,
    *,
    no_store: bool = False,
    data_dir: Path | None = None,
) -> FileResponse:
    data_dir = (data_dir or current_data_dir(get_settings().data_dir)).resolve()
    target = (data_dir / file_path).resolve()
    if data_dir not in target.parents and target != data_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if target.name in PRIVATE_DATA_FILENAMES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    headers = {"Cache-Control": "no-store"} if no_store else None
    return FileResponse(target, headers=headers)


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

    try:
        context = auth_context_from_bearer_token(session, raw_api_token)
    except HTTPException:
        return False
    return "admin" in context.scopes or "notes:read" in context.scopes


def _published_markdown_response(file_path: str, session: Session) -> FileResponse:
    if file_path.startswith("sources/") or "/sources/" in file_path:
        return _published_source_response(file_path, session)

    paths = workspace_paths_for_session(session)
    data_dir = paths.data_dir.resolve()
    target = (data_dir / "markdown" / file_path).resolve()
    if data_dir not in target.parents and target != data_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    notes = session.scalars(
        select(Note).options(selectinload(Note.folder)).where(Note.is_published.is_(True))
    ).all()
    for note in notes:
        if paths.note_file_path(note).resolve() == target:
            return _file_response(f"markdown/{file_path}", data_dir=data_dir)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


def _published_source_response(file_path: str, session: Session) -> FileResponse:
    paths = workspace_paths_for_session(session)
    data_dir = paths.data_dir.resolve()
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
        if paths.source_file_path(source_file).resolve() == target:
            return _file_response(f"markdown/{file_path}", data_dir=data_dir)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.get("/html", include_in_schema=False)
@router.get("/html/", include_in_schema=False)
def get_published_html_root() -> FileResponse:
    return _file_response("html/index.html", no_store=True)


@router.get("/html/workspaces/{workspace_id}", include_in_schema=False)
@router.get("/html/workspaces/{workspace_id}/", include_in_schema=False)
def get_workspace_published_html_root(workspace_id: str) -> FileResponse:
    return _file_response(
        "html/index.html",
        no_store=True,
        data_dir=workspace_by_id(workspace_id).folder_path,
    )


@router.get("/html/workspaces/{workspace_id}/latest", include_in_schema=False)
@router.get("/html/workspaces/{workspace_id}/latest/", include_in_schema=False)
def get_workspace_published_latest_root(workspace_id: str) -> FileResponse:
    return _file_response(
        "html/latest/index.html",
        no_store=True,
        data_dir=workspace_by_id(workspace_id).folder_path,
    )


@router.get(
    "/html/workspaces/{workspace_id}/{file_path:path}",
    name="get_workspace_published_html_file",
    include_in_schema=False,
)
def get_workspace_published_html_file(workspace_id: str, file_path: str) -> FileResponse:
    return _file_response(
        f"html/{_clean_file_path(file_path)}",
        no_store=True,
        data_dir=workspace_by_id(workspace_id).folder_path,
    )


@router.get("/html/latest", include_in_schema=False)
@router.get("/html/latest/", include_in_schema=False)
def get_published_latest_root() -> FileResponse:
    return _file_response("html/latest/index.html", no_store=True)


@router.get("/html/{file_path:path}", include_in_schema=False)
def get_published_html_file(file_path: str) -> FileResponse:
    return _file_response(f"html/{_clean_file_path(file_path)}", no_store=True)


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
    data_dir = workspace_paths_for_session(session).data_dir
    if _has_authenticated_file_access(request, session):
        return _file_response(f"markdown/{clean}", data_dir=data_dir)
    return _published_markdown_response(clean, session)


@router.get("/.profiles/{file_path:path}", include_in_schema=False)
def get_profile_file(file_path: str, _user: NotesReadUser) -> FileResponse:
    clean = _clean_file_path(file_path)
    return _file_response(f".profiles/{clean}", data_dir=get_settings().data_dir)


@router.get("/{file_path:path}", name="get_folder_file")
def get_folder_file(file_path: str, session: SessionDep, user: NotesReadUser) -> FileResponse:
    return _file_response(file_path, data_dir=workspace_paths_for_session(session).data_dir)
