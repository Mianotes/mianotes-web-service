from __future__ import annotations

from sqlalchemy.engine import Engine

from .models import Base
from .session import engine


def create_database(target_engine: Engine = engine) -> None:
    Base.metadata.create_all(bind=target_engine)

