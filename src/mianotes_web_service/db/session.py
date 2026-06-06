from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Cookie, Header, Request
from sqlalchemy.orm import Session, sessionmaker

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


def _testing_session_factory(request: Request | None) -> sessionmaker[Session] | None:
    if request is None:
        return None
    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    return getattr(state, "testing_session_factory", None)


def get_system_session(request: Request) -> Generator[Session, None, None]:
    session_factory = _testing_session_factory(request) or system_sessionmaker()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def workspace_session_context(
    workspace,
    request: Request | None = None,
) -> Generator[Session, None, None]:
    session_factory = _testing_session_factory(request) or sessionmaker_for_workspace(workspace)
    session = session_factory()
    session.info["workspace"] = workspace
    token = set_current_workspace(workspace)
    try:
        yield session
    finally:
        session.close()
        reset_current_workspace(token)


def open_workspace_session(
    workspace,
    request: Request | None = None,
) -> Generator[Session, None, None]:
    with workspace_session_context(workspace, request) as session:
        yield session


def get_session(
    request: Request,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    x_mianotes_workspace: Annotated[str | None, Header(alias="X-Mianotes-Workspace")] = None,
) -> Generator[Session, None, None]:
    workspace = resolve_workspace(
        session_token=session_token,
        workspace_header=x_mianotes_workspace,
    )
    yield from open_workspace_session(workspace, request)
