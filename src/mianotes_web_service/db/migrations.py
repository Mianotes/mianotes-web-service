from __future__ import annotations

from collections.abc import Sequence

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, String, Text, inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.sql.schema import Table

from .models import Base
from .schema import SYSTEM_TABLES, WORKSPACE_TABLES


def _existing_columns(connection: Connection, table_name: str) -> set[str]:
    inspector = inspect(connection)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(
    connection: Connection,
    operations: Operations,
    table_name: str,
    column: Column,
) -> None:
    columns = _existing_columns(connection, table_name)
    if columns and column.name not in columns:
        operations.add_column(table_name, column)


def _run_legacy_compatibility_migrations(connection: Connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    _add_column_if_missing(connection, operations, "users", Column("password_hash", Text()))
    _add_column_if_missing(
        connection,
        operations,
        "session_tokens",
        Column("workspace_id", String(120)),
    )
    _add_column_if_missing(
        connection,
        operations,
        "mia_jobs",
        Column("client_key", String(80)),
    )
    _add_column_if_missing(
        connection,
        operations,
        "mia_jobs",
        Column("client_name", String(120)),
    )


def run_table_migrations(target_engine: Engine, tables: Sequence[Table]) -> None:
    Base.metadata.create_all(bind=target_engine, tables=tables)
    with target_engine.begin() as connection:
        _run_legacy_compatibility_migrations(connection)


def run_system_migrations(target_engine: Engine) -> None:
    run_table_migrations(target_engine, SYSTEM_TABLES)


def run_workspace_migrations(target_engine: Engine) -> None:
    run_table_migrations(target_engine, WORKSPACE_TABLES)


def run_all_migrations(target_engine: Engine) -> None:
    run_table_migrations(target_engine, (*SYSTEM_TABLES, *WORKSPACE_TABLES))
