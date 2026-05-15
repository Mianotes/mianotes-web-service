from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from mianotes_web_service.api.dependencies import AuthContextDep, SessionDep
from mianotes_web_service.db.models import ApiToken, User
from mianotes_web_service.domain.schemas import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from mianotes_web_service.services.auth import (
    create_api_token,
    decode_api_token_scopes,
    normalize_api_token_scopes,
)

router = APIRouter(prefix="/tokens", tags=["tokens"])


def _token_response(token: ApiToken, *, raw_token: str | None = None) -> ApiTokenRead:
    payload = {
        "id": token.id,
        "user": token.user,
        "name": token.name,
        "token_prefix": token.token_prefix,
        "scopes": decode_api_token_scopes(token.scopes),
        "created_at": token.created_at,
        "updated_at": token.updated_at,
        "last_used_at": token.last_used_at,
        "expires_at": token.expires_at,
        "revoked_at": token.revoked_at,
    }
    if raw_token is not None:
        return ApiTokenCreated(**payload, token=raw_token)
    return ApiTokenRead(**payload)


def _can_manage_tokens(context: AuthContextDep) -> None:
    if context.is_browser_session or "admin" in context.scopes or "tokens:write" in context.scopes:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="API token requires tokens:write scope",
    )


def _can_read_tokens(context: AuthContextDep) -> None:
    if context.is_browser_session or "admin" in context.scopes or "tokens:read" in context.scopes:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="API token requires tokens:read scope",
    )


@router.post("", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(
    payload: ApiTokenCreate,
    session: SessionDep,
    context: AuthContextDep,
) -> ApiTokenCreated:
    _can_manage_tokens(context)
    token_user_id = payload.user_id or context.user.id
    if token_user_id != context.user.id and not context.user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create tokens for other users",
        )
    token_user = session.get(User, token_user_id)
    if token_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        scopes = normalize_api_token_scopes(payload.scopes)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    token, raw_token = create_api_token(
        session,
        token_user,
        name=payload.name,
        scopes=scopes,
        expires_at=payload.expires_at,
    )
    session.commit()
    session.refresh(token)
    return _token_response(token, raw_token=raw_token)


@router.get("", response_model=list[ApiTokenRead])
def list_tokens(
    session: SessionDep,
    context: AuthContextDep,
    user_id: Annotated[str | None, Query()] = None,
    include_revoked: Annotated[bool, Query()] = False,
) -> list[ApiTokenRead]:
    _can_read_tokens(context)
    if user_id is not None and user_id != context.user.id and not context.user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can list tokens for other users",
        )
    statement = select(ApiToken).order_by(ApiToken.created_at.desc())
    statement = statement.where(ApiToken.user_id == (user_id or context.user.id))
    if not include_revoked:
        statement = statement.where(ApiToken.revoked_at.is_(None))
    return [_token_response(token) for token in session.scalars(statement)]


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(token_id: str, session: SessionDep, context: AuthContextDep) -> None:
    _can_manage_tokens(context)
    token = session.get(ApiToken, token_id)
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    if token.user_id != context.user.id and not context.user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can revoke tokens for other users",
        )
    token.revoked_at = datetime.now(UTC)
    session.commit()
