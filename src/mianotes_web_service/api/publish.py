from __future__ import annotations

import re
import zipfile
from io import BytesIO

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from mianotes_web_service.api.dependencies import NotesReadUser, NotesWriteUser, SessionDep
from mianotes_web_service.db.models import PublishedSite
from mianotes_web_service.domain.schemas import (
    PublishDraftRead,
    PublishRead,
    PublishRequest,
    PublishThemeRead,
)
from mianotes_web_service.services.publishing import (
    build_publish_draft,
    list_publish_themes,
    publish_site,
)
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.storage_settings import DEFAULT_LOCATION_ID
from mianotes_web_service.services.workspace_context import session_workspace

router = APIRouter(prefix="/publish", tags=["publish"])


@router.get("/themes", response_model=list[PublishThemeRead])
def read_publish_themes(user: NotesReadUser) -> list[PublishThemeRead]:
    _ = user
    return [
        PublishThemeRead(
            id=theme.id,
            name=theme.name,
            description=theme.description,
            version=theme.version,
        )
        for theme in list_publish_themes()
    ]


@router.get("/draft", response_model=PublishDraftRead)
def read_publish_draft(
    session: SessionDep,
    user: NotesReadUser,
    theme: str = "mialight",
    folder_id: str | None = None,
    tag_id: str | None = None,
) -> PublishDraftRead:
    _ = user
    draft = build_publish_draft(session, theme_id=theme, folder_id=folder_id, tag_id=tag_id)
    return PublishDraftRead(
        theme=draft.theme,
        folder_id=draft.folder_id,
        tag_id=draft.tag_id,
        site_configuration=draft.site_configuration,
        navigation=draft.navigation,
        updated_notes=draft.updated_notes,
        generated_at=draft.generated_at,
    )


@router.post("", response_model=PublishRead, status_code=status.HTTP_201_CREATED)
def publish_site_endpoint(
    payload: PublishRequest,
    request: Request,
    session: SessionDep,
    user: NotesWriteUser,
) -> PublishRead:
    published_site = publish_site(session, user, payload)
    workspace = session_workspace(session)
    workspace_id = workspace.id if workspace is not None else DEFAULT_LOCATION_ID
    site_url = str(
        request.url_for(
            "get_workspace_published_html_file",
            workspace_id=workspace_id,
            file_path=published_site.url_path.removeprefix("html/"),
        )
    )
    download_url = str(request.url_for("download_published_site", site_id=published_site.id))
    return PublishRead(
        id=published_site.id,
        theme=published_site.theme,
        version=published_site.version,
        folder_id=published_site.folder_id,
        tag_id=published_site.tag_id,
        note_count=published_site.note_count,
        html_path=published_site.html_path,
        markdown_path=published_site.markdown_path,
        url_path=published_site.url_path,
        site_url=site_url,
        download_url=download_url,
        created_at=published_site.created_at,
    )


@router.get("/{site_id}/download", name="download_published_site")
def download_published_site(
    site_id: str,
    session: SessionDep,
    user: NotesReadUser,
) -> StreamingResponse:
    _ = user
    site = session.get(PublishedSite, site_id)
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published site not found",
        )

    data_dir = workspace_paths_for_session(session).data_dir
    html_root = (data_dir / "html").resolve()
    site_dir = (data_dir / site.html_path).resolve()
    if html_root not in site_dir.parents or not site_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published site files not found",
        )

    archive = BytesIO()
    archive_root = f"{_archive_name(site)}-static-site"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in (
            html_root / "index.html",
            html_root / "navigation.js",
            html_root / "README.md",
        ):
            if file_path.is_file():
                zip_file.write(file_path, f"{archive_root}/{file_path.name}")
        for file_path in sorted(path for path in site_dir.rglob("*") if path.is_file()):
            zip_file.write(
                file_path,
                f"{archive_root}/{file_path.relative_to(html_root).as_posix()}",
            )
    archive.seek(0)

    filename = f"{archive_root}.zip"
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _archive_name(site: PublishedSite) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", site.version.strip()).strip(".-_")
    return value or "mianotes"
