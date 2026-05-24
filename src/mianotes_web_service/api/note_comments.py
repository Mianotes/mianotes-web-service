from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import CommentsWriteUser, NotesReadUser
from mianotes_web_service.api.note_access import read_note_or_404
from mianotes_web_service.db.models import Comment
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import (
    CommentCreate,
    CommentRead,
    CommentUpdate,
    MiaPromptRead,
)
from mianotes_web_service.services.mia import MiaUnavailable
from mianotes_web_service.services.paths import note_file_path
from mianotes_web_service.services.storage import markdown_note_body

router = APIRouter(prefix="/notes", tags=["notes"])
SessionDep = Annotated[Session, Depends(get_session)]


def _mia_prompt(body: str) -> str | None:
    stripped = body.strip()
    if not stripped.lower().startswith("@mia"):
        return None
    prompt = stripped[4:].strip()
    if not prompt:
        raise HTTPException(
            status_code=422,
            detail="Mia prompt cannot be empty",
        )
    return prompt


@router.get("/{note_id}/comments")
def get_note_comments(
    note_id: str,
    session: SessionDep,
    user: NotesReadUser,
) -> list[CommentRead]:
    note = read_note_or_404(session, note_id)
    return [
        CommentRead.model_validate(comment)
        for comment in sorted(note.comments, key=lambda item: item.created_at)
        if comment.body
    ]


@router.post(
    "/{note_id}/comments",
    response_model=CommentRead | MiaPromptRead,
    status_code=status.HTTP_201_CREATED,
)
def create_note_comment(
    note_id: str,
    payload: CommentCreate,
    response: Response,
    session: SessionDep,
    user: CommentsWriteUser,
) -> Comment | MiaPromptRead:
    note = read_note_or_404(session, note_id)
    prompt = _mia_prompt(payload.body)
    if prompt is not None:
        try:
            raw_markdown = (
                payload.markdown
                if payload.markdown is not None
                else note_file_path(note).read_text(encoding="utf-8")
            )
            from mianotes_web_service.api import notes as notes_api

            result = notes_api.prompt_markdown(
                title=note.title,
                markdown=markdown_note_body(raw_markdown) or raw_markdown,
                prompt=prompt,
            )
        except MiaUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # pragma: no cover - provider/network boundary
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Mia prompt failed",
            ) from exc
        response.status_code = status.HTTP_200_OK
        return MiaPromptRead(
            prompt=prompt,
            note_id=note.id,
            text=result.text,
        )

    response.status_code = status.HTTP_201_CREATED
    comment = Comment(note_id=note.id, user_id=user.id, body=payload.body)
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return comment


@router.patch("/{note_id}/comments/{comment_id}", response_model=CommentRead)
def update_note_comment(
    note_id: str,
    comment_id: str,
    payload: CommentUpdate,
    session: SessionDep,
    user: CommentsWriteUser,
) -> Comment:
    read_note_or_404(session, note_id)
    comment = session.get(Comment, comment_id)
    if comment is None or comment.note_id != note_id or not comment.body:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if not user.is_admin and comment.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change this comment",
        )
    comment.body = payload.body
    session.commit()
    session.refresh(comment)
    return comment


@router.delete("/{note_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_comment(
    note_id: str,
    comment_id: str,
    session: SessionDep,
    user: CommentsWriteUser,
) -> None:
    read_note_or_404(session, note_id)
    comment = session.get(Comment, comment_id)
    if comment is None or comment.note_id != note_id or not comment.body:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if not user.is_admin and comment.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change this comment",
        )
    session.delete(comment)
    session.commit()
