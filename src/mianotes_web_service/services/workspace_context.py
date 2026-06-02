from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mianotes_web_service.services.storage_settings import DEFAULT_LOCATION_ID


@dataclass(frozen=True)
class WorkspaceContext:
    id: str
    name: str
    folder_path: Path


_current_workspace: ContextVar[WorkspaceContext | None] = ContextVar(
    "mianotes_current_workspace",
    default=None,
)


def set_current_workspace(workspace: WorkspaceContext | None) -> Token[WorkspaceContext | None]:
    return _current_workspace.set(workspace)


def reset_current_workspace(token: Token[WorkspaceContext | None]) -> None:
    try:
        _current_workspace.reset(token)
    except ValueError:
        _current_workspace.set(None)


def current_workspace() -> WorkspaceContext | None:
    return _current_workspace.get()


def current_workspace_id() -> str:
    workspace = current_workspace()
    return workspace.id if workspace is not None else DEFAULT_LOCATION_ID


def current_data_dir(default: Path) -> Path:
    workspace = current_workspace()
    return workspace_data_dir(default, workspace)


def workspace_data_dir(default: Path, workspace: WorkspaceContext | None) -> Path:
    return workspace.folder_path if workspace is not None else default


def session_workspace(session: Any) -> WorkspaceContext | None:
    workspace = getattr(session, "info", {}).get("workspace")
    return workspace if isinstance(workspace, WorkspaceContext) else None


def session_data_dir(session: Any, default: Path) -> Path:
    return workspace_data_dir(default, session_workspace(session))
