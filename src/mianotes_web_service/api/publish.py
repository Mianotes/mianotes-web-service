from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from mianotes_web_service.api.dependencies import NotesReadUser, NotesWriteUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import PublishedSite
from mianotes_web_service.domain.schemas import (
    PublishDraftRead,
    PublishRead,
    PublishRequest,
    PublishThemeRead,
)
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.published_downloads import (
    PublishedSiteDownloadLimitError,
    PublishedSiteFilesNotFoundError,
    build_published_site_archive,
    stream_file_and_remove,
)
from mianotes_web_service.services.publishing import (
    build_publish_draft,
    list_publish_themes,
    publish_site,
)
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

    settings = get_settings()
    try:
        archive = build_published_site_archive(
            site,
            data_dir=workspace_paths_for_session(session).data_dir,
            max_bytes=settings.max_published_site_download_bytes,
            max_files=settings.max_published_site_download_files,
        )
    except PublishedSiteFilesNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published site files not found",
        ) from None
    except PublishedSiteDownloadLimitError:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Published site is too large to download as a ZIP.",
        ) from None

    return StreamingResponse(
        stream_file_and_remove(archive.path),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{archive.filename}"'},
    )
