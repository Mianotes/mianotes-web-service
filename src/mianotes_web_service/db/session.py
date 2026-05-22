from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from mianotes_web_service.core.config import get_settings


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


settings = get_settings()
assert settings.database_url is not None


def create_database_engine(database_url: str) -> Engine:
    _prepare_sqlite_database(database_url)
    return create_engine(database_url, connect_args=_connect_args(database_url))


engine = create_database_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def reconfigure_database(database_url: str) -> Engine:
    global engine

    new_engine = create_database_engine(database_url)
    old_engine = engine
    engine = new_engine
    SessionLocal.configure(bind=new_engine)
    old_engine.dispose()
    return new_engine


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
