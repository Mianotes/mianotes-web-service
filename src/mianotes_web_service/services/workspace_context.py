from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from mianotes_web_service.services.storage_settings import DEFAULT_LOCATION_ID


@dataclass(frozen=True)
class WorkspaceContext:
    id: str
    name: str
    folder_path: Path
    database_file: str


_current_workspace: ContextVar[WorkspaceContext | None] = ContextVar(
    "mianotes_current_workspace",
    default=None,
)


def set_current_workspace(workspace: WorkspaceContext):
    return _current_workspace.set(workspace)


def reset_current_workspace(token) -> None:
    _current_workspace.reset(token)


def current_workspace() -> WorkspaceContext | None:
    return _current_workspace.get()


def current_workspace_id() -> str:
    workspace = current_workspace()
    return workspace.id if workspace is not None else DEFAULT_LOCATION_ID


def current_data_dir(default: Path) -> Path:
    workspace = current_workspace()
    return workspace.folder_path if workspace is not None else default
