from __future__ import annotations

from fastapi import APIRouter, Request, status

from mianotes_web_service.api.dependencies import NotesReadUser, NotesWriteUser, SessionDep
from mianotes_web_service.domain.schemas import (
    PublishDraftRead,
    PublishPreviewRead,
    PublishRead,
    PublishRequest,
    PublishThemeRead,
)
from mianotes_web_service.services.publishing import (
    build_publish_draft,
    list_publish_themes,
    preview_publish,
    publish_site,
)

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
    theme: str = "mianotes",
    folder_id: str | None = None,
) -> PublishDraftRead:
    _ = user
    draft = build_publish_draft(session, theme_id=theme, folder_id=folder_id)
    return PublishDraftRead(
        theme=draft.theme,
        folder_id=draft.folder_id,
        site_configuration=draft.site_configuration,
        navigation=draft.navigation,
        updated_notes=draft.updated_notes,
        generated_at=draft.generated_at,
    )


@router.post("/preview", response_model=PublishPreviewRead)
def preview_publish_site(
    payload: PublishRequest,
    session: SessionDep,
    user: NotesReadUser,
) -> PublishPreviewRead:
    _ = user
    note_count, output_path = preview_publish(session, payload)
    return PublishPreviewRead(
        theme=payload.theme,
        folder_id=payload.folder_id,
        note_count=note_count,
        output_path=output_path,
    )


@router.post("", response_model=PublishRead, status_code=status.HTTP_201_CREATED)
def publish_site_endpoint(
    payload: PublishRequest,
    request: Request,
    session: SessionDep,
    user: NotesWriteUser,
) -> PublishRead:
    published_site = publish_site(session, user, payload)
    site_url = str(request.url_for("get_folder_file", file_path=published_site.url_path))
    return PublishRead(
        id=published_site.id,
        theme=published_site.theme,
        version=published_site.version,
        folder_id=published_site.folder_id,
        note_count=published_site.note_count,
        html_path=published_site.html_path,
        markdown_path=published_site.markdown_path,
        url_path=published_site.url_path,
        site_url=site_url,
        created_at=published_site.created_at,
    )
