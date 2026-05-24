from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mianotes_web_service.db.models import Comment, Note, User
from mianotes_web_service.services.share import get_share_secret, hash_share_token


def read_note_or_404(session: Session, note_id: str) -> Note:
    statement = (
        select(Note)
        .where(Note.id == note_id)
        .options(
            joinedload(Note.user),
            joinedload(Note.folder),
            joinedload(Note.source_files),
            joinedload(Note.comments).joinedload(Comment.user),
            joinedload(Note.tags),
            joinedload(Note.jobs),
        )
    )
    note = session.scalars(statement).unique().one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


def read_note_by_share_token(session: Session, token: str) -> Note:
    secret = get_share_secret(session)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared note not found")
    token_hash = hash_share_token(secret, token)
    statement = (
        select(Note)
        .where(Note.share_token_hash == token_hash, Note.shared_at.is_not(None))
        .options(
            joinedload(Note.user),
            joinedload(Note.folder),
            joinedload(Note.source_files),
            joinedload(Note.comments).joinedload(Comment.user),
            joinedload(Note.tags),
        )
    )
    note = session.scalars(statement).unique().one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared note not found")
    return note


def ensure_can_change_note(note: Note, user: User) -> None:
    if user.is_admin or note.user_id == user.id:
        return
    owner_name = note.user.name if note.user is not None else "the note owner"
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Only {owner_name} or an admin can change this note.",
    )
