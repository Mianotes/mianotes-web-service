from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import NotesWriteUser
from mianotes_web_service.api.note_access import read_note_reference
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import MiaPromptCreate, MiaPromptRead
from mianotes_web_service.services.mia import MiaUnavailable, prompt_markdown
from mianotes_web_service.services.paths import workspace_paths_for_session
from mianotes_web_service.services.storage import markdown_note_body

router = APIRouter(prefix="/notes", tags=["notes"])
SessionDep = Annotated[Session, Depends(get_session)]
MIA_PROVIDER_SETUP_MESSAGE = "Mia needs an AI provider before it can answer prompts."
logger = logging.getLogger(__name__)


@router.post(
    "/{note_id}/prompt",
    response_model=MiaPromptRead,
    status_code=status.HTTP_200_OK,
)
def prompt_note(
    note_id: str,
    payload: MiaPromptCreate,
    response: Response,
    session: SessionDep,
    user: NotesWriteUser,
) -> MiaPromptRead:
    note = read_note_reference(session, note_id)
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mia prompt cannot be empty",
        )

    try:
        paths = workspace_paths_for_session(session)
        raw_markdown = (
            payload.markdown
            if payload.markdown is not None
            else paths.note_file_path(note).read_text(encoding="utf-8")
        )
        result = prompt_markdown(
            title=note.title,
            markdown=markdown_note_body(raw_markdown) or raw_markdown,
            prompt=prompt,
        )
    except MiaUnavailable as exc:
        logger.info("Mia prompt unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=MIA_PROVIDER_SETUP_MESSAGE,
        ) from exc
    except Exception as exc:  # pragma: no cover - provider/network boundary
        logger.exception("Mia prompt failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=MIA_PROVIDER_SETUP_MESSAGE,
        ) from exc

    response.status_code = status.HTTP_200_OK
    return MiaPromptRead(
        prompt=prompt,
        note_id=note.id,
        text=result.text,
    )
