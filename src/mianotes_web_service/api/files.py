from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

from mianotes_web_service.api.dependencies import NotesReadUser
from mianotes_web_service.services.file_serving import (
    serve_profile_file,
    serve_public_markdown_file,
    serve_published_html_file,
    serve_published_html_root,
    serve_published_latest_root,
    serve_workspace_note_image,
    serve_workspace_note_markdown,
    serve_workspace_published_html_file,
    serve_workspace_published_html_root,
    serve_workspace_published_latest_root,
    serve_workspace_source_file,
)

router = APIRouter(tags=["files"])


@router.get("/html", include_in_schema=False)
@router.get("/html/", include_in_schema=False)
def get_published_html_root() -> FileResponse:
    return serve_published_html_root()


@router.get("/html/workspaces/{workspace_id}", include_in_schema=False)
@router.get("/html/workspaces/{workspace_id}/", include_in_schema=False)
def get_workspace_published_html_root(workspace_id: str) -> FileResponse:
    return serve_workspace_published_html_root(workspace_id)


@router.get("/html/workspaces/{workspace_id}/latest", include_in_schema=False)
@router.get("/html/workspaces/{workspace_id}/latest/", include_in_schema=False)
def get_workspace_published_latest_root(workspace_id: str) -> FileResponse:
    return serve_workspace_published_latest_root(workspace_id)


@router.get(
    "/html/workspaces/{workspace_id}/{file_path:path}",
    name="get_workspace_published_html_file",
    include_in_schema=False,
)
def get_workspace_published_html_file(workspace_id: str, file_path: str) -> FileResponse:
    return serve_workspace_published_html_file(workspace_id, file_path)


@router.get("/html/latest", include_in_schema=False)
@router.get("/html/latest/", include_in_schema=False)
def get_published_latest_root() -> FileResponse:
    return serve_published_latest_root()


@router.get("/html/{file_path:path}", include_in_schema=False)
def get_published_html_file(file_path: str) -> FileResponse:
    return serve_published_html_file(file_path)


@router.get("/markdown", include_in_schema=False)
@router.get("/markdown/", include_in_schema=False)
def get_markdown_root() -> FileResponse:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.get("/markdown/{file_path:path}", include_in_schema=False)
def get_markdown_file(
    file_path: str,
    request: Request,
) -> FileResponse:
    return serve_public_markdown_file(file_path, request)


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
    return serve_workspace_note_markdown(workspace_id, note_id, request)


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
    return serve_workspace_source_file(workspace_id, note_id, source_file_id, request)


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
    return serve_workspace_note_image(workspace_id, note_id, file_path, request)


@router.get("/.profiles/{file_path:path}", include_in_schema=False)
def get_profile_file(file_path: str, _user: NotesReadUser) -> FileResponse:
    return serve_profile_file(file_path)
