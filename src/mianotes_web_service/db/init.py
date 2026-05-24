from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .models import Base
from .session import engine


def _add_missing_columns(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    with target_engine.begin() as connection:
        if "password_hash" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT"))


def create_database(target_engine: Engine = engine) -> None:
    Base.metadata.create_all(bind=target_engine)
    _add_missing_columns(target_engine)
