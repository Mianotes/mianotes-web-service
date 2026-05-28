from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Cookie, Header, Request
from sqlalchemy.orm import Session

from mianotes_web_service.db.workspace_routing import (
    resolve_workspace,
    sessionmaker_for_workspace,
    system_sessionmaker,
)
from mianotes_web_service.services.auth import SESSION_COOKIE_NAME
from mianotes_web_service.services.workspace_context import (
    reset_current_workspace,
    set_current_workspace,
)


def get_system_session() -> Generator[Session, None, None]:
    session = system_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def get_session(
    request: Request,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    x_mianotes_workspace: Annotated[str | None, Header(alias="X-Mianotes-Workspace")] = None,
) -> Generator[Session, None, None]:
    workspace = resolve_workspace(
        session_token=session_token,
        workspace_header=x_mianotes_workspace,
    )
    session_factory = sessionmaker_for_workspace(workspace)
    session = session_factory()
    session.info["workspace"] = workspace
    token = set_current_workspace(workspace)
    try:
        yield session
    finally:
        session.close()
        reset_current_workspace(token)
