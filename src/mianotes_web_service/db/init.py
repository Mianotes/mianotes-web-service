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
