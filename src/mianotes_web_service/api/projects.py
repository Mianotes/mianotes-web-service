from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mianotes_web_service.api.dependencies import ProjectsReadUser, ProjectsWriteUser
from mianotes_web_service.db.models import Project
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import ProjectCreate, ProjectRead
from mianotes_web_service.services.storage import slugify

router = APIRouter(prefix="/projects", tags=["projects"])
SessionDep = Annotated[Session, Depends(get_session)]


def _read_project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: SessionDep, user: ProjectsWriteUser) -> Project:
    project = Project(user_id=user.id, name=payload.name, slug=slugify(payload.name))
    session.add(project)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A project with this name already exists for this user",
        ) from exc
    session.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(
    session: SessionDep,
    user: ProjectsReadUser,
    user_id: Annotated[str | None, Query()] = None,
    include_archived: Annotated[bool, Query()] = False,
) -> list[Project]:
    statement = select(Project).order_by(Project.created_at.desc())
    if user_id is not None:
        statement = statement.where(Project.user_id == user_id)
    if not include_archived:
        statement = statement.where(Project.archived_at.is_(None))
    return list(session.scalars(statement))


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, session: SessionDep, user: ProjectsReadUser) -> Project:
    return _read_project_or_404(session, project_id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_project(project_id: str, session: SessionDep, user: ProjectsWriteUser) -> None:
    project = _read_project_or_404(session, project_id)
    if not user.is_admin and project.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot archive this project",
        )
    project.archived_at = datetime.now(UTC)
    project.archived_by_user_id = user.id
    session.commit()
