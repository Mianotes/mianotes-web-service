from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import User
from mianotes_web_service.db.session import get_system_session, open_workspace_session
from mianotes_web_service.db.workspace_routing import resolve_workspace
from mianotes_web_service.services.auth import (
    SESSION_COOKIE_NAME,
    read_session_user,
)
from mianotes_web_service.services.auth_context import (
    AuthContext,
    auth_context_from_bearer_token,
    read_bearer_token,
)
from mianotes_web_service.services.workspace_access import ensure_workspace_access
from mianotes_web_service.services.workspace_context import WorkspaceContext

SystemSessionDep = Annotated[Session, Depends(get_system_session)]


def current_auth_context(
    session: SystemSessionDep,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    raw_api_token = read_bearer_token(authorization)
    if raw_api_token is not None:
        return auth_context_from_bearer_token(session, raw_api_token)

    user = read_session_user(session, session_token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    return AuthContext(user=user)


AuthContextDep = Annotated[AuthContext, Depends(current_auth_context)]


def current_workspace_context(
    context: AuthContextDep,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    x_mianotes_workspace: Annotated[str | None, Header(alias="X-Mianotes-Workspace")] = None,
) -> WorkspaceContext:
    workspace = resolve_workspace(
        session_token=session_token,
        workspace_header=x_mianotes_workspace,
    )
    ensure_workspace_access(context.user, workspace)
    return workspace


CurrentWorkspace = Annotated[WorkspaceContext, Depends(current_workspace_context)]


def get_authorized_workspace_session(
    request: Request,
    workspace: CurrentWorkspace,
) -> Generator[Session, None, None]:
    yield from open_workspace_session(workspace, request)


WorkspaceSessionDep = Annotated[Session, Depends(get_authorized_workspace_session)]
SessionDep = WorkspaceSessionDep


def current_user(context: AuthContextDep) -> User:
    return context.user


CurrentUser = Annotated[User, Depends(current_user)]


def require_scope(scope: str):
    def dependency(context: AuthContextDep) -> User:
        if context.is_browser_session or "admin" in context.scopes or scope in context.scopes:
            return context.user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API token requires {scope} scope",
        )

    return dependency


UsersReadUser = Annotated[User, Depends(require_scope("users:read"))]
FoldersReadUser = Annotated[User, Depends(require_scope("folders:read"))]
FoldersWriteUser = Annotated[User, Depends(require_scope("folders:write"))]
NotesReadUser = Annotated[User, Depends(require_scope("notes:read"))]
NotesWriteUser = Annotated[User, Depends(require_scope("notes:write"))]
TagsReadUser = Annotated[User, Depends(require_scope("tags:read"))]
TagsWriteUser = Annotated[User, Depends(require_scope("tags:write"))]
ShareWriteUser = Annotated[User, Depends(require_scope("share:write"))]


def require_admin(context: AuthContextDep) -> User:
    if not context.user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    if not context.is_browser_session and "admin" not in context.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API token requires admin scope",
        )
    return context.user


AdminUser = Annotated[User, Depends(require_admin)]
