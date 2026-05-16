from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .models import Base
from .session import engine


def create_database(target_engine: Engine = engine) -> None:
    _upgrade_sqlite_schema(target_engine)
    Base.metadata.create_all(bind=target_engine)
    _upgrade_sqlite_schema(target_engine)


def _sqlite_table_names(connection) -> set[str]:
    return set(
        connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")).scalars()
    )


def _sqlite_columns(connection, table_name: str) -> set[str]:
    return {row[1] for row in connection.execute(text(f"PRAGMA table_info({table_name})"))}


def _upgrade_sqlite_schema(target_engine: Engine) -> None:
    if target_engine.dialect.name != "sqlite":
        return
    with target_engine.begin() as connection:
        table_names = _sqlite_table_names(connection)
        if "topics" in table_names and "projects" not in table_names:
            connection.execute(text("ALTER TABLE topics RENAME TO projects"))
            table_names = _sqlite_table_names(connection)

        if "users" in table_names:
            columns = _sqlite_columns(connection, "users")
            if "is_admin" not in columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
                )
        if "projects" in table_names:
            columns = _sqlite_columns(connection, "projects")
            if "archived_at" not in columns:
                connection.execute(text("ALTER TABLE projects ADD COLUMN archived_at DATETIME"))
            if "archived_by_user_id" not in columns:
                connection.execute(
                    text("ALTER TABLE projects ADD COLUMN archived_by_user_id VARCHAR(36)")
                )
        if "notes" in table_names:
            columns = _sqlite_columns(connection, "notes")
            if "topic_id" in columns and "project_id" not in columns:
                connection.execute(text("ALTER TABLE notes RENAME COLUMN topic_id TO project_id"))
                columns = _sqlite_columns(connection, "notes")
            if "status" not in columns:
                connection.execute(
                    text("ALTER TABLE notes ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'ready'")
                )
            if "source_type" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE notes ADD COLUMN source_type "
                        "VARCHAR(50) NOT NULL DEFAULT 'text'"
                    )
                )
            if "revision_number" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE notes ADD COLUMN revision_number "
                        "INTEGER NOT NULL DEFAULT 1"
                    )
                )
            if "is_published" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE notes ADD COLUMN is_published "
                        "BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
            if "published_at" not in columns:
                connection.execute(text("ALTER TABLE notes ADD COLUMN published_at DATETIME"))
            if "share_token_hash" not in columns:
                connection.execute(
                    text("ALTER TABLE notes ADD COLUMN share_token_hash VARCHAR(128)")
                )
            if "shared_at" not in columns:
                connection.execute(text("ALTER TABLE notes ADD COLUMN shared_at DATETIME"))
        if "comments" in table_names:
            columns = _sqlite_columns(connection, "comments")
            if "user_id" not in columns:
                connection.execute(text("ALTER TABLE comments ADD COLUMN user_id VARCHAR(36)"))
            if "body" not in columns:
                connection.execute(text("ALTER TABLE comments ADD COLUMN body TEXT"))
