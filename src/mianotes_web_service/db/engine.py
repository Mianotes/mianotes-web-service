from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine


def _connect_args(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _prepare_sqlite_database(database_url: str) -> None:
    if not database_url.startswith("sqlite") or database_url.endswith(":memory:"):
        return
    if ":///" not in database_url:
        return
    path = Path(database_url.split(":///", 1)[1])
    path.parent.mkdir(parents=True, exist_ok=True)


def _is_file_sqlite_database(database_url: str) -> bool:
    return (
        database_url.startswith("sqlite")
        and not database_url.endswith(":memory:")
        and ":///" in database_url
    )


def _configure_sqlite_pragmas(engine: Engine, database_url: str) -> None:
    if not _is_file_sqlite_database(database_url):
        return

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def create_database_engine(database_url: str) -> Engine:
    _prepare_sqlite_database(database_url)
    engine = create_engine(database_url, connect_args=_connect_args(database_url))
    _configure_sqlite_pragmas(engine, database_url)
    return engine
