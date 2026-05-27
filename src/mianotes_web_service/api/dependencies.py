from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import ApiToken, AppSetting, User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.services.agent_clients import AgentClient, resolve_agent_client
from mianotes_web_service.services.auth import (
    INSTANCE_API_TOKEN_PUBLIC_KEY,
    SESSION_COOKIE_NAME,
    decode_agent_session_token,
    decode_api_token_scopes,
    read_api_token,
    read_session_user,
    sync_instance_api_token_public_key,
    verify_instance_api_token,
)

SessionDep = Annotated[Session, Depends(get_session)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    token: ApiToken | None = None
    is_instance_token: bool = False
    client_name: str | None = None
    client_key: str | None = None

    @property
    def scopes(self) -> set[str]:
        if self.is_instance_token:
            return {"admin"}
        if self.token is None:
            return set()
        return set(decode_api_token_scopes(self.token.scopes))

    @property
    def is_browser_session(self) -> bool:
        return self.token is None and not self.is_instance_token

    @property
    def agent_client(self) -> AgentClient | None:
        if self.client_key is None:
            return None
        return AgentClient(key=self.client_key, name=self.client_name or self.client_key)


def _read_bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _read_instance_token_context(session: Session, raw_api_token: str) -> AuthContext | None:
    settings = get_settings()
    if settings.api_token:
        sync_instance_api_token_public_key(session, settings.api_token)
    if not verify_instance_api_token(session, raw_api_token):
        return None

    admin_user = session.scalars(
        select(User).where(User.is_admin.is_(True)).order_by(User.created_at.asc())
    ).first()
    if admin_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "The service API token is valid, but this database has no admin user yet. "
                "Complete first-user setup before using API token access."
            ),
        )
    return AuthContext(user=admin_user, is_instance_token=True)


def _read_agent_session_context(session: Session, raw_token: str) -> AuthContext | None:
    payload = decode_agent_session_token(session, raw_token)
    if payload is None:
        return None

    user_id = payload.get("user_id") or payload.get("sub")
    client_name = payload.get("client")
    client_key = payload.get("client_key")
    if not isinstance(user_id, str) or not isinstance(client_name, str):
        return None
    if not isinstance(client_key, str):
        agent_client = resolve_agent_client(client_name)
        client_name = agent_client.name
        client_key = agent_client.key

    api_token_id = payload.get("api_token_id")
    if isinstance(api_token_id, str):
        api_token = session.get(ApiToken, api_token_id)
        if api_token is None or api_token.revoked_at is not None:
            return None
        if api_token.user_id != user_id:
            return None
        return AuthContext(
            user=api_token.user,
            token=api_token,
            client_name=client_name,
            client_key=client_key,
        )

    instance_token_public_key = payload.get("instance_token_public_key")
    if not isinstance(instance_token_public_key, str):
        return None
    setting = session.get(AppSetting, INSTANCE_API_TOKEN_PUBLIC_KEY)
    if setting is None or setting.value != instance_token_public_key:
        return None

    user = session.get(User, user_id)
    if user is None:
        return None
    return AuthContext(
        user=user,
        is_instance_token=True,
        client_name=client_name,
        client_key=client_key,
    )


def auth_context_from_bearer_token(session: Session, raw_api_token: str) -> AuthContext:
    if "." in raw_api_token:
        agent_context = _read_agent_session_context(session, raw_api_token)
        if agent_context is not None:
            return agent_context

    api_token = read_api_token(session, raw_api_token)
    if api_token is not None:
        return AuthContext(user=api_token.user, token=api_token)

    instance_context = _read_instance_token_context(session, raw_api_token)
    if instance_context is not None:
        return instance_context

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API token",
    )


def current_auth_context(
    session: SessionDep,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    raw_api_token = _read_bearer_token(authorization)
    if raw_api_token is not None:
        return auth_context_from_bearer_token(session, raw_api_token)

    user = read_session_user(session, session_token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    return AuthContext(user=user)


AuthContextDep = Annotated[AuthContext, Depends(current_auth_context)]


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
CommentsWriteUser = Annotated[User, Depends(require_scope("comments:write"))]
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
