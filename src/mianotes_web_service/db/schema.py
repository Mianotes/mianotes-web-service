from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Table

from .models import (
    ApiToken,
    AppSetting,
    Base,
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


def create_tables(target_engine: Engine, tables: Sequence[Table]) -> None:
    Base.metadata.create_all(bind=target_engine, tables=tables)


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
