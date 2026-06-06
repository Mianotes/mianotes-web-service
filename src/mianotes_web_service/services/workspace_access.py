from __future__ import annotations

from fastapi import HTTPException, status

from mianotes_web_service.db.models import User
from mianotes_web_service.services.workspace_context import WorkspaceContext


def can_access_workspace(user: User, workspace: WorkspaceContext) -> bool:
    """Central workspace access policy.

    Mianotes currently has global users and all configured workspaces are available
    to signed-in users. Keeping this check in one place gives the future membership
    model a single backend gateway instead of scattered UI or route checks.
    """
    return bool(user.id and workspace.id)


def ensure_workspace_access(user: User, workspace: WorkspaceContext) -> None:
    if can_access_workspace(user, workspace):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Workspace access denied",
    )
