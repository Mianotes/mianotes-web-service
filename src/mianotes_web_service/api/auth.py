from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import CurrentUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Folder, Note, SourceFile, User, new_id
from mianotes_web_service.domain.schemas import (
    AdminKeyRead,
    AdminKeyResetRequest,
    EmailCheck,
    EmailCheckResult,
    JoinRequest,
    LoginRequest,
    SessionRead,
)
from mianotes_web_service.services.auth import (
    SESSION_COOKIE_NAME,
    create_admin_key,
    create_session_token,
    get_master_password_hash,
    is_admin_key_enabled,
    set_master_password,
    verify_admin_key,
    verify_master_password,
)
from mianotes_web_service.services.storage import FilesystemStorage, make_username

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=60 * 60 * 24 * 90,
        httponly=True,
        samesite="lax",
    )


def _create_onboarding_note(session: Session, user: User) -> None:
    existing_folder = session.scalars(
        select(Folder).where(Folder.slug == "mianotes")
    ).one_or_none()
    if existing_folder is not None:
        return

    folder = Folder(user_id=user.id, name="Mianotes", slug="mianotes", path="mianotes")
    session.add(folder)
    session.flush()
    text = (
        "Welcome to Mianotes. Add text, links, documents, images, and audio to turn "
        "them into organised Markdown notes. Everyone with access to this instance "
        "can browse shared notes, while owners keep control of their own contributions."
    )
    storage = FilesystemStorage(get_settings().data_dir)
    note_id = new_id()
    paths = storage.write_text_note(
        username=user.username,
        folder=folder.path,
        title="How to use Mianotes",
        text=text,
        filename=note_id,
    )
    note = Note(
        id=note_id,
        user_id=user.id,
        folder_id=folder.id,
        title="How to use Mianotes",
        filename=paths.note_path.name,
        note_path=str(paths.note_path),
    )
    session.add(note)
    session.flush()
    if paths.source_path is not None:
        session.add(
            SourceFile(
                note_id=note.id,
                filename=str(paths.source_path.relative_to(paths.directory)),
                file_path=str(paths.source_path),
                original_filename="original.txt",
                content_type="text/plain",
            )
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


def _is_local_request(request: Request) -> bool:
    if request.client is None:
        return False
    return request.client.host in {"127.0.0.1", "::1", "localhost", "testclient"}


@router.post("/check-email", response_model=EmailCheckResult)
def check_email(payload: EmailCheck, session: SessionDep) -> EmailCheckResult:
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
            admin_key_required=user.is_admin and is_admin_key_enabled(session),
        )
    return EmailCheckResult(user_id=None, master_password_owner_name=master_password_owner_name)


@router.post("/join", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def join(payload: JoinRequest, response: Response, session: SessionDep) -> SessionRead:
    email = str(payload.email).lower()
    admin_key: str | None = None

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
        set_master_password(session, payload.password)
        admin_key = create_admin_key(session) if payload.shared_instance else None
        session.flush()
        _create_onboarding_note(session, user)
    else:
        if not verify_master_password(session, payload.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
        if session.scalars(select(User).where(User.email == email)).one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

        user = User(
            email=email,
            name=payload.name,
            username=make_username(email, payload.name),
            is_admin=False,
        )
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
    return SessionRead(user=user, admin_key=admin_key)


@router.post("/login", response_model=SessionRead)
def login(payload: LoginRequest, response: Response, session: SessionDep) -> SessionRead:
    user = session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not verify_master_password(session, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    if user.is_admin and is_admin_key_enabled(session):
        if payload.admin_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin key is required",
            )
        if not verify_admin_key(session, payload.admin_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin key",
            )
    token = create_session_token(session, user)
    session.commit()
    _set_session_cookie(response, token.id)
    return SessionRead(user=user)


@router.get("/session", response_model=SessionRead)
def session_info(user: CurrentUser) -> SessionRead:
    return SessionRead(user=user)


@router.post("/admin-key/reset-local", response_model=AdminKeyRead)
def reset_admin_key_locally(
    payload: AdminKeyResetRequest,
    request: Request,
    session: SessionDep,
) -> AdminKeyRead:
    if not _is_local_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin key reset is only available from the Mianotes host machine",
        )
    user = session.get(User, payload.user_id)
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found")
    if not verify_master_password(session, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    admin_key = create_admin_key(session)
    session.commit()
    return AdminKeyRead(admin_key=admin_key)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)
