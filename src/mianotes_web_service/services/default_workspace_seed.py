from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Note
from mianotes_web_service.services.workspace_markdown_import import (
    import_compatible_markdown_notes,
)

SEED_PACKAGE = "mianotes_web_service"
SEED_ROOT = ("seed", "default_workspace")


def seed_default_workspace(
    session: Session,
    *,
    workspace_folder: Path,
    user_id: str,
) -> int:
    """Seed an empty workspace with bundled Markdown, then index it normally."""
    note_count = session.scalar(select(func.count()).select_from(Note)) or 0
    if note_count > 0:
        return 0

    _copy_seed_files(workspace_folder)
    return import_compatible_markdown_notes(
        session,
        workspace_folder=workspace_folder,
        user_id=user_id,
    )


def _copy_seed_files(workspace_folder: Path) -> None:
    seed_root = resources.files(SEED_PACKAGE).joinpath(*SEED_ROOT)
    _copy_resource_tree(seed_root, workspace_folder)


def _copy_resource_tree(source: Traversable, destination: Path) -> None:
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            _copy_resource_tree(item, target)
        elif item.is_file():
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())
