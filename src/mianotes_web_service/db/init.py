from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .models import Base
from .session import engine


def create_database(target_engine: Engine = engine) -> None:
    Base.metadata.create_all(bind=target_engine)
    _upgrade_sqlite_schema(target_engine)


def _upgrade_sqlite_schema(target_engine: Engine) -> None:
    if target_engine.dialect.name != "sqlite":
        return
    inspector = inspect(target_engine)
    table_names = set(inspector.get_table_names())
    with target_engine.begin() as connection:
        if "users" in table_names:
            columns = {column["name"] for column in inspector.get_columns("users")}
            if "is_admin" not in columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
                )
        if "topics" in table_names:
            columns = {column["name"] for column in inspector.get_columns("topics")}
            if "archived_at" not in columns:
                connection.execute(text("ALTER TABLE topics ADD COLUMN archived_at DATETIME"))
            if "archived_by_user_id" not in columns:
                connection.execute(
                    text("ALTER TABLE topics ADD COLUMN archived_by_user_id VARCHAR(36)")
                )
        if "notes" in table_names:
            columns = {column["name"] for column in inspector.get_columns("notes")}
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
            columns = {column["name"] for column in inspector.get_columns("comments")}
            if "user_id" not in columns:
                connection.execute(text("ALTER TABLE comments ADD COLUMN user_id VARCHAR(36)"))
            if "body" not in columns:
                connection.execute(text("ALTER TABLE comments ADD COLUMN body TEXT"))
