from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class FilesystemRollbackError(RuntimeError):
    """Raised when compensating filesystem actions cannot restore a failed commit."""


class FilesystemUnitOfWork:
    def __init__(self) -> None:
        self._rollback_actions: list[Callable[[], None]] = []
        self._cleanup_actions: list[Callable[[], None]] = []

    def move_path(self, current_path: Path, target_path: Path) -> None:
        current_path = current_path.resolve()
        target_path = target_path.resolve()
        if current_path == target_path:
            return
        if not current_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note file not found",
            )
        if target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A file already exists in the target folder",
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(current_path), str(target_path))
        self._rollback_actions.append(lambda: self._move_existing_path(target_path, current_path))

    def create_text(self, target_path: Path, content: str, *, encoding: str = "utf-8") -> None:
        if target_path.exists():
            return
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding=encoding)
        self._rollback_actions.append(lambda: target_path.unlink(missing_ok=True))

    def replace_text(self, target_path: Path, content: str, *, encoding: str = "utf-8") -> None:
        self.replace_bytes(target_path, content.encode(encoding))

    def delete_path(self, target_path: Path) -> None:
        target_path = target_path.resolve()
        if not target_path.exists():
            return

        backup_dir = Path(tempfile.mkdtemp(prefix="mianotes-delete-backup-"))
        backup_path = backup_dir / target_path.name
        shutil.move(str(target_path), str(backup_path))
        self._rollback_actions.append(lambda: self._move_existing_path(backup_path, target_path))
        self._cleanup_actions.append(lambda: self._remove_path(backup_dir))

    def replace_bytes(self, target_path: Path, content: bytes) -> None:
        target_path = target_path.resolve()
        if target_path.exists() and not target_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not update note file",
            )

        backup_path: Path | None = None
        if target_path.exists():
            backup_fd, backup_name = tempfile.mkstemp(prefix="mianotes-file-backup-")
            os.close(backup_fd)
            backup_path = Path(backup_name)
            shutil.copy2(target_path, backup_path)
            self._cleanup_actions.append(lambda: backup_path.unlink(missing_ok=True))

        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_name = tempfile.mkstemp(
            prefix=f".{target_path.name}.",
            dir=target_path.parent,
        )
        os.close(temp_fd)
        temp_path = Path(temp_name)
        try:
            temp_path.write_bytes(content)
            temp_path.replace(target_path)
        finally:
            temp_path.unlink(missing_ok=True)

        if backup_path is None:
            self._rollback_actions.append(lambda: target_path.unlink(missing_ok=True))
        else:
            self._rollback_actions.append(
                lambda: self._restore_file_backup(backup_path, target_path)
            )

    def rollback(self) -> None:
        errors: list[Exception] = []
        for action in reversed(self._rollback_actions):
            try:
                action()
            except Exception as exc:  # pragma: no cover - defensive aggregation
                errors.append(exc)
        self._rollback_actions.clear()
        self._cleanup()
        if errors:
            raise FilesystemRollbackError("Could not roll back filesystem changes") from errors[0]

    def clear(self) -> None:
        self._cleanup()
        self._rollback_actions.clear()

    def _cleanup(self) -> None:
        for action in reversed(self._cleanup_actions):
            try:
                action()
            except OSError:
                pass
        self._cleanup_actions.clear()

    @staticmethod
    def _move_existing_path(current_path: Path, target_path: Path) -> None:
        if not current_path.exists():
            return
        if target_path.exists():
            return
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(current_path), str(target_path))

    @staticmethod
    def _restore_file_backup(backup_path: Path, target_path: Path) -> None:
        if backup_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(backup_path), str(target_path))

    @staticmethod
    def _remove_path(target_path: Path) -> None:
        if target_path.is_dir():
            shutil.rmtree(target_path)
        else:
            target_path.unlink(missing_ok=True)


def commit_with_filesystem_rollback(
    session: Session,
    filesystem: FilesystemUnitOfWork,
    *,
    error_detail: str = "Could not save changes",
) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        filesystem.rollback()
        raise
    except Exception as exc:
        session.rollback()
        filesystem.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        ) from exc
    filesystem.clear()
