from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .models import Base
from .session import engine


def _add_missing_columns(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    with target_engine.begin() as connection:
        if "password_hash" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT"))
        if "mia_jobs" in tables:
            job_columns = {column["name"] for column in inspector.get_columns("mia_jobs")}
            if "client_key" not in job_columns:
                connection.execute(text("ALTER TABLE mia_jobs ADD COLUMN client_key VARCHAR(80)"))
            if "client_name" not in job_columns:
                connection.execute(text("ALTER TABLE mia_jobs ADD COLUMN client_name VARCHAR(120)"))


def create_database(target_engine: Engine = engine) -> None:
    Base.metadata.create_all(bind=target_engine)
    _add_missing_columns(target_engine)
