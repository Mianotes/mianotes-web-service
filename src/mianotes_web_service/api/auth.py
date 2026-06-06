from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import (
    CurrentUser,
    SystemSessionDep,
)
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import AppSetting, SessionToken, User
from mianotes_web_service.db.session import workspace_session_context
from mianotes_web_service.db.workspace_routing import default_workspace
from mianotes_web_service.domain.schemas import (
    AgentSessionRead,
    EmailCheck,
    EmailCheckResult,
    JoinRequest,
    LoginRequest,
    SessionRead,
)
from mianotes_web_service.services.agent_clients import AgentClient
from mianotes_web_service.services.auth import (
    INSTANCE_API_TOKEN_PUBLIC_KEY,
    SESSION_COOKIE_NAME,
    WORKSPACE_ACCESS_MODE_ADMIN_ONLY,
    WORKSPACE_ACCESS_MODE_OPEN,
    create_agent_session_token,
    create_session_token,
    decode_api_token_scopes,
    get_master_password_hash,
    get_workspace_access_mode,
    set_master_password,
    set_user_password,
    set_workspace_access_mode,
    verify_master_password,
    verify_user_password,
)
from mianotes_web_service.services.auth_context import (
    auth_context_from_bearer_token,
    read_bearer_token,
)
from mianotes_web_service.services.onboarding import create_onboarding_note
from mianotes_web_service.services.storage import make_username
from mianotes_web_service.services.user_limits import enforce_user_capacity
from mianotes_web_service.services.workspace_context import current_data_dir

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=60 * 60 * 24 * 90,
        httponly=True,
        samesite="lax",
        secure=get_settings().session_cookie_secure,
    )


def _instance_initialized(session: Session) -> bool:
    admin_count = session.scalar(
        select(func.count()).select_from(User).where(User.is_admin.is_(True))
    )
    return bool(admin_count) or get_master_password_hash(session) is not None


def _master_password_owner_name(session: Session) -> str | None:
    admin = session.scalars(
        select(User).where(User.is_admin.is_(True)).order_by(User.created_at.asc())
    ).first()
    return admin.name if admin is not None else None


@router.post("/check-email", response_model=EmailCheckResult)
def check_email(payload: EmailCheck, session: SystemSessionDep) -> EmailCheckResult:
    if not _instance_initialized(session):
        return EmailCheckResult(user_id=None, is_first_user=True)

    user = session.scalars(
        select(User).where(User.email == str(payload.email).lower())
    ).one_or_none()
    master_password_owner_name = _master_password_owner_name(session)
    if user is not None:
        return EmailCheckResult(
            user_id=user.id,
            master_password_owner_name=master_password_owner_name,
        )
    signup_disabled = get_workspace_access_mode(session) == WORKSPACE_ACCESS_MODE_ADMIN_ONLY
    return EmailCheckResult(
        user_id=None,
        master_password_owner_name=master_password_owner_name,
        signup_disabled=signup_disabled,
    )


@router.post("/join", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def join(
    payload: JoinRequest,
    response: Response,
    request: Request,
    session: SystemSessionDep,
) -> SessionRead:
    email = str(payload.email).lower()

    if not _instance_initialized(session):
        if payload.password_confirmation is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password confirmation is required for the first user",
            )
        if payload.password != payload.password_confirmation:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Passwords do not match",
            )
        user = session.scalars(select(User).where(User.email == email)).one_or_none()
        if user is None:
            user = User(
                email=email,
                name=payload.name,
                username=make_username(email, payload.name),
                is_admin=True,
            )
            session.add(user)
        else:
            user.name = payload.name
            user.is_admin = True
        set_user_password(user, payload.password)
        set_master_password(session, payload.password)
        access_mode = payload.workspace_access_mode or WORKSPACE_ACCESS_MODE_OPEN
        try:
            set_workspace_access_mode(session, access_mode)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        session.flush()
        with workspace_session_context(default_workspace(), request) as onboarding_session:
            try:
                create_onboarding_note(
                    onboarding_session,
                    user,
                    data_dir=current_data_dir(get_settings().data_dir),
                )
                onboarding_session.commit()
            except Exception:
                onboarding_session.rollback()
                raise
    else:
        if get_workspace_access_mode(session) == WORKSPACE_ACCESS_MODE_ADMIN_ONLY:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This workspace is limited to the admin account",
            )
        if session.scalars(select(User).where(User.email == email)).one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")
        if payload.password_confirmation is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password confirmation is required",
            )
        if payload.password != payload.password_confirmation:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Passwords do not match",
            )
        enforce_user_capacity(session, get_settings())

        user = User(
            email=email,
            name=payload.name,
            username=make_username(email, payload.name),
            is_admin=False,
        )
        set_user_password(user, payload.password)
        session.add(user)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already exists",
            ) from exc

    token = create_session_token(session, user)
    session.commit()
    _set_session_cookie(response, token.id)
    session.refresh(user)
    return SessionRead(user=user)


@router.post("/login", response_model=SessionRead)
def login(payload: LoginRequest, response: Response, session: SystemSessionDep) -> SessionRead:
    user = session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.password_hash:
        valid_password = verify_user_password(user, payload.password)
    else:
        valid_password = verify_master_password(session, payload.password)
        if valid_password:
            set_user_password(user, payload.password)
    if not valid_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    token = create_session_token(session, user)
    session.commit()
    _set_session_cookie(response, token.id)
    return SessionRead(user=user)


@router.get("/session", response_model=SessionRead)
def session_info(user: CurrentUser) -> SessionRead:
    return SessionRead(user=user)


@router.post("/agent-session", response_model=AgentSessionRead, status_code=status.HTTP_201_CREATED)
def create_agent_session(
    session: SystemSessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AgentSessionRead:
    raw_api_token = read_bearer_token(authorization)
    if raw_api_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key is required")

    context = auth_context_from_bearer_token(session, raw_api_token)
    if context.is_browser_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key is required")
    agent_client = AgentClient(key="api", name=context.user.email)

    if context.is_instance_token:
        scopes = ["admin"]
        instance_token_public_key = session.get(AppSetting, INSTANCE_API_TOKEN_PUBLIC_KEY)
        if instance_token_public_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API token",
            )
        session_token, expires_at = create_agent_session_token(
            session,
            user=context.user,
            client_name=agent_client.name,
            client_key=agent_client.key,
            scopes=scopes,
            instance_token_public_key=instance_token_public_key.value,
        )
    else:
        assert context.token is not None
        scopes = decode_api_token_scopes(context.token.scopes)
        session_token, expires_at = create_agent_session_token(
            session,
            user=context.user,
            client_name=agent_client.name,
            client_key=agent_client.key,
            scopes=scopes,
            api_token_id=context.token.id,
        )

    session.commit()
    return AgentSessionRead(
        token=session_token,
        client_key=agent_client.key,
        client=agent_client.name,
        expires_at=expires_at,
        user=context.user,
        scopes=scopes,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session: SystemSessionDep,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> None:
    if session_token:
        token = session.get(SessionToken, session_token)
        if token is not None:
            session.delete(token)
            session.commit()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        secure=get_settings().session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
