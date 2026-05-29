from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Table

from .models import Base
from .schema import SYSTEM_TABLES, WORKSPACE_TABLES


def run_table_migrations(target_engine: Engine, tables: Sequence[Table]) -> None:
    Base.metadata.create_all(bind=target_engine, tables=tables)


def run_system_migrations(target_engine: Engine) -> None:
    run_table_migrations(target_engine, SYSTEM_TABLES)


def run_workspace_migrations(target_engine: Engine) -> None:
    run_table_migrations(target_engine, WORKSPACE_TABLES)


def run_all_migrations(target_engine: Engine) -> None:
    run_table_migrations(target_engine, (*SYSTEM_TABLES, *WORKSPACE_TABLES))
