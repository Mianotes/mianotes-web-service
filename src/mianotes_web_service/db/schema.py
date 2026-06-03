from __future__ import annotations

from .models import (
    ApiToken,
    AppSetting,
    Folder,
    MiaJob,
    Note,
    NoteStar,
    NoteTag,
    PublishedSite,
    SessionToken,
    SourceFile,
    Tag,
    User,
)

SYSTEM_TABLES = (
    User.__table__,
    SessionToken.__table__,
    ApiToken.__table__,
    AppSetting.__table__,
)
WORKSPACE_TABLES = (
    Folder.__table__,
    Note.__table__,
    PublishedSite.__table__,
    SourceFile.__table__,
    Tag.__table__,
    NoteTag.__table__,
    NoteStar.__table__,
    MiaJob.__table__,
)
