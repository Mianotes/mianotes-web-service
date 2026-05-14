from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import CurrentUser, SessionDep
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Comment, Note, SourceFile, Topic, User, new_id
from mianotes_web_service.domain.schemas import (
    EmailCheck,
    JoinRequest,
    LoginRequest,
    SessionRead,
)
from mianotes_web_service.services.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    get_master_password_hash,
    set_master_password,
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
    existing_topic = session.scalars(
        select(Topic).where(Topic.user_id == user.id, Topic.slug == "mianotes")
    ).one_or_none()
    if existing_topic is not None:
        return

    topic = Topic(user_id=user.id, name="Mianotes", slug="mianotes")
    session.add(topic)
    session.flush()
    text = (
        "Welcome to Mianotes. Add text, links, documents, images, and audio to turn "
        "them into organised Markdown notes. Everyone in your household can browse "
        "shared notes, while owners keep control of their own contributions."
    )
    storage = FilesystemStorage(get_settings().data_dir)
    note_id = new_id()
    paths = storage.write_text_note(
        username=user.username,
        topic=topic.slug,
        title="How to use Mianotes",
        text=text,
        filename=note_id,
    )
    note = Note(
        id=note_id,
        user_id=user.id,
        topic_id=topic.id,
        title="How to use Mianotes",
        note_path=str(paths.note_path),
    )
    session.add(note)
    session.flush()
    if paths.source_path is not None:
        session.add(
            SourceFile(
                note_id=note.id,
                file_path=str(paths.source_path),
                original_filename="how-to-use-mianotes.source.txt",
                content_type="text/plain",
            )
        )
    session.add(Comment(note_id=note.id, comments_path=str(paths.comments_path)))


def _household_initialized(session: Session) -> bool:
    admin_count = session.scalar(
        select(func.count()).select_from(User).where(User.is_admin.is_(True))
    )
    return bool(admin_count) or get_master_password_hash(session) is not None


@router.post("/check-email")
def check_email(payload: EmailCheck, session: SessionDep) -> dict[str, bool | str | None]:
    if not _household_initialized(session):
        return {"user_id": None, "is_first_user": True}

    user = session.scalars(
        select(User).where(User.email == str(payload.email).lower())
    ).one_or_none()
    if user is not None:
        return {"user_id": user.id}
    return {"user_id": None}


@router.post("/join", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def join(payload: JoinRequest, response: Response, session: SessionDep) -> SessionRead:
    email = str(payload.email).lower()

    if not _household_initialized(session):
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
                username=make_username(email),
                is_admin=True,
            )
            session.add(user)
        else:
            user.name = payload.name
            user.is_admin = True
        set_master_password(session, payload.password)
        session.flush()
        _create_onboarding_note(session, user)
    else:
        if not verify_master_password(session, payload.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
        if session.scalars(select(User).where(User.email == email)).one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

        user = User(email=email, name=payload.name, username=make_username(email), is_admin=False)
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
def login(payload: LoginRequest, response: Response, session: SessionDep) -> SessionRead:
    user = session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not verify_master_password(session, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    token = create_session_token(session, user)
    session.commit()
    _set_session_cookie(response, token.id)
    return SessionRead(user=user)


@router.get("/session", response_model=SessionRead)
def session_info(user: CurrentUser) -> SessionRead:
    return SessionRead(user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)
