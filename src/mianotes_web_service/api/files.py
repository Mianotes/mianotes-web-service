from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.api.dependencies import (
    NotesReadUser,
    SessionDep,
    auth_context_from_bearer_token,
)
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Folder, Note, SourceFile
from mianotes_web_service.db.workspace_routing import (
    sessionmaker_for_workspace,
    workspace_by_id,
)
from mianotes_web_service.services.auth import SESSION_COOKIE_NAME, read_session_user
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.storage_settings import (
    DEFAULT_LOCATION_ID,
    SQLITE_SIDECAR_SUFFIXES,
    SYSTEM_DATABASE_FILENAME,
)
from mianotes_web_service.services.workspace_context import (
    WorkspaceContext,
    current_data_dir,
    reset_current_workspace,
    set_current_workspace,
)

router = APIRouter(tags=["files"])
PRIVATE_DATA_FILENAMES = {
    SYSTEM_DATABASE_FILENAME,
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
    if target.name in PRIVATE_DATA_FILENAMES or target.name.endswith(
        (".db", *(f".db{suffix}" for suffix in SQLITE_SIDECAR_SUFFIXES))
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    headers = {"Cache-Control": "no-store"} if no_store else None
    return FileResponse(target, headers=headers)


def _inline_markdown_response(target: Path) -> FileResponse:
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(
        target,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{target.name}"',
        },
    )


def _known_file_response(
    target: Path,
    *,
    root: Path,
    no_store: bool = False,
    media_type: str | None = None,
) -> FileResponse:
    root = root.resolve()
    target = target.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from exc
    if target.name in PRIVATE_DATA_FILENAMES or target.name.endswith(
        (".db", *(f".db{suffix}" for suffix in SQLITE_SIDECAR_SUFFIXES))
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    headers = {"Cache-Control": "no-store"} if no_store else None
    return FileResponse(target, media_type=media_type, headers=headers)


def _clean_file_path(file_path: str) -> str:
    clean = file_path.strip("/")
    if not clean:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return clean


def _markdown_target(file_path: str, data_dir: Path) -> Path:
    target = (data_dir / "markdown" / file_path).resolve()
    if data_dir not in target.parents and target != data_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return target


def _folder_file_parts(file_path: str) -> tuple[str, str]:
    folder_path, separator, filename = file_path.rpartition("/")
    if not separator or not folder_path or not filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return folder_path, filename


def _source_file_parts(file_path: str) -> tuple[str, str]:
    folder_path, separator, source_path = file_path.partition("/sources/")
    if not separator or not folder_path or not source_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return folder_path, f"sources/{source_path}"


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


def _session_for_workspace(workspace: WorkspaceContext, request: Request) -> Session:
    testing_session_factory = getattr(request.app.state, "testing_session_factory", None)
    if testing_session_factory is not None and workspace.id == DEFAULT_LOCATION_ID:
        session = testing_session_factory()
    else:
        session = sessionmaker_for_workspace(workspace)()
    session.info["workspace"] = workspace
    return session


@contextmanager
def _workspace_session(workspace_id: str, request: Request) -> Generator[Session, None, None]:
    workspace = workspace_by_id(workspace_id)
    token = set_current_workspace(workspace)
    session = _session_for_workspace(workspace, request)
    try:
        yield session
    finally:
        session.close()
        reset_current_workspace(token)


def _note_markdown_response(note: Note, session: Session) -> FileResponse:
    paths = workspace_paths_for_session(session)
    markdown_root = paths.markdown_root.resolve()
    target = paths.note_file_path(note).resolve()
    try:
        target.relative_to(markdown_root)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from exc
    return _inline_markdown_response(target)


def _note_or_404(session: Session, note_id: str) -> Note:
    note = session.scalars(
        select(Note)
        .options(joinedload(Note.folder))
        .where(Note.id == note_id)
        .limit(1)
    ).one_or_none()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )
    return note


def _published_markdown_response(file_path: str, session: Session) -> FileResponse:
    if file_path.startswith("sources/") or "/sources/" in file_path:
        return _published_source_response(file_path, session)

    paths = workspace_paths_for_session(session)
    data_dir = paths.data_dir.resolve()
    _markdown_target(file_path, data_dir)

    folder_path, filename = _folder_file_parts(file_path)
    note_id = session.scalars(
        select(Note.id)
        .join(Note.folder)
        .where(
            Note.is_published.is_(True),
            Note.filename == filename,
            Folder.path == folder_path,
        )
        .limit(1)
    ).first()
    if note_id is not None:
        return _file_response(f"markdown/{file_path}", data_dir=data_dir)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


def _published_source_response(file_path: str, session: Session) -> FileResponse:
    paths = workspace_paths_for_session(session)
    data_dir = paths.data_dir.resolve()
    _markdown_target(file_path, data_dir)

    folder_path, source_filename = _source_file_parts(file_path)
    source_file_id = session.scalars(
        select(SourceFile.id)
        .join(SourceFile.note)
        .join(Note.folder)
        .where(
            Note.is_published.is_(True),
            SourceFile.filename == source_filename,
            Folder.path == folder_path,
        )
        .limit(1)
    ).first()
    if source_file_id is not None:
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
    session: SessionDep,
) -> FileResponse:
    clean = _clean_file_path(file_path)
    return _published_markdown_response(clean, session)


@router.get(
    "/api/workspaces/{workspace_id}/notes/{note_id}/markdown",
    name="get_workspace_note_markdown_file",
    include_in_schema=False,
)
@router.get(
    "/api/workspaces/{workspace_id}/markdown/{note_id}",
    name="get_legacy_workspace_note_markdown_file",
    include_in_schema=False,
)
def get_workspace_note_markdown_file(
    workspace_id: str,
    note_id: str,
    request: Request,
) -> FileResponse:
    with _workspace_session(workspace_id, request) as session:
        if not _has_authenticated_file_access(request, session):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not signed in",
            )
        return _note_markdown_response(_note_or_404(session, note_id), session)


@router.get(
    "/api/workspaces/{workspace_id}/notes/{note_id}/source-files/{source_file_id}",
    name="get_workspace_source_file",
    include_in_schema=False,
)
def get_workspace_source_file(
    workspace_id: str,
    note_id: str,
    source_file_id: str,
    request: Request,
) -> FileResponse:
    with _workspace_session(workspace_id, request) as session:
        if not _has_authenticated_file_access(request, session):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not signed in",
            )
        source_file = session.scalars(
            select(SourceFile)
            .options(joinedload(SourceFile.note).joinedload(Note.folder))
            .where(SourceFile.id == source_file_id, SourceFile.note_id == note_id)
            .limit(1)
        ).one_or_none()
        if source_file is None or source_file.note is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        paths = workspace_paths_for_session(session)
        return _known_file_response(
            paths.source_file_path(source_file),
            root=paths.markdown_root,
            no_store=True,
        )


@router.get(
    "/api/workspaces/{workspace_id}/notes/{note_id}/images/{file_path:path}",
    name="get_workspace_note_image",
    include_in_schema=False,
)
def get_workspace_note_image(
    workspace_id: str,
    note_id: str,
    file_path: str,
    request: Request,
) -> FileResponse:
    clean = _clean_file_path(file_path)
    with _workspace_session(workspace_id, request) as session:
        if not _has_authenticated_file_access(request, session):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not signed in",
            )
        note = _note_or_404(session, note_id)
        paths = workspace_paths_for_session(session)
        image_root = paths.note_image_directory(note)
        return _known_file_response(
            image_root / clean,
            root=image_root,
            no_store=True,
        )


@router.get("/.profiles/{file_path:path}", include_in_schema=False)
def get_profile_file(file_path: str, _user: NotesReadUser) -> FileResponse:
    clean = _clean_file_path(file_path)
    return _file_response(f".profiles/{clean}", data_dir=get_settings().data_dir)
