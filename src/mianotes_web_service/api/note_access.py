from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from mianotes_web_service.db.models import Note, User
from mianotes_web_service.services.share import get_share_secret, hash_share_token


def _read_note_or_404(session: Session, note_id: str, *, options=()) -> Note:
    statement = select(Note).where(Note.id == note_id)
    if options:
        statement = statement.options(*options)
    note = session.scalars(statement).one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


def _read_shared_note_or_404(session: Session, token: str, *, options=()) -> Note:
    secret = get_share_secret(session)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared note not found")
    token_hash = hash_share_token(secret, token)
    statement = (
        select(Note)
        .where(Note.share_token_hash == token_hash, Note.shared_at.is_not(None))
    )
    if options:
        statement = statement.options(*options)
    note = session.scalars(statement).one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared note not found")
    return note


def _response_options():
    return (
        selectinload(Note.user),
        joinedload(Note.folder),
        selectinload(Note.source_files),
        selectinload(Note.tags),
        selectinload(Note.jobs),
    )


def read_note_reference(session: Session, note_id: str) -> Note:
    return _read_note_or_404(session, note_id)


def read_note_for_response(session: Session, note_id: str) -> Note:
    return _read_note_or_404(session, note_id, options=_response_options())


def read_note_for_change(session: Session, note_id: str) -> Note:
    return _read_note_or_404(
        session,
        note_id,
        options=(
            selectinload(Note.user),
            joinedload(Note.folder),
        ),
    )


def read_note_for_tag_change(session: Session, note_id: str) -> Note:
    return _read_note_or_404(
        session,
        note_id,
        options=(
            selectinload(Note.user),
            joinedload(Note.folder),
            selectinload(Note.tags),
        ),
    )


def read_note_for_delete(session: Session, note_id: str) -> Note:
    return _read_note_or_404(
        session,
        note_id,
        options=(
            selectinload(Note.user),
            joinedload(Note.folder),
            selectinload(Note.source_files),
        ),
    )


def read_shared_note_for_response(session: Session, token: str) -> Note:
    return _read_shared_note_or_404(session, token, options=_response_options())


def read_shared_note_for_avatar(session: Session, token: str) -> Note:
    return _read_shared_note_or_404(session, token, options=(selectinload(Note.user),))


def read_shared_note_for_source_file(session: Session, token: str) -> Note:
    return _read_shared_note_or_404(session, token, options=(selectinload(Note.source_files),))


def ensure_can_change_note(note: Note, user: User) -> None:
    if user.is_admin or note.user_id == user.id:
        return
    owner_name = note.user.name if note.user is not None else "the note owner"
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Only {owner_name} or an admin can change this note.",
    )
