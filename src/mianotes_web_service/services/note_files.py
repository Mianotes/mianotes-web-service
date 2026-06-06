from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Folder, Note, User
from mianotes_web_service.services.filesystem_uow import FilesystemUnitOfWork
from mianotes_web_service.services.note_deletion import stage_note_files_for_delete
from mianotes_web_service.services.note_moves import move_note_to_folder
from mianotes_web_service.services.paths import WorkspacePaths, workspace_paths_for_session
from mianotes_web_service.services.storage import (
    FilesystemStorage,
    NotePaths,
    render_markdown_note,
    replace_markdown_title,
)


class NoteFiles:
    """Filesystem operations for notes in the current workspace.

    Routers should keep database policy and response shaping, while this service
    owns path resolution and staged note-file mutations.
    """

    def __init__(self, session: Session) -> None:
        self.paths = workspace_paths_for_session(session)
        self.storage = FilesystemStorage(self.paths.data_dir)

    @property
    def data_dir(self) -> Path:
        return self.paths.data_dir

    def create_text_note(
        self,
        *,
        user: User,
        folder: Folder,
        title: str,
        text: str,
        note_id: str,
    ) -> NotePaths:
        return self.storage.write_text_note(
            username=user.username,
            folder=folder.path,
            title=title,
            text=text,
            filename=note_id,
        )

    def create_uploaded_file_note(
        self,
        *,
        user: User,
        folder: Folder,
        title: str,
        note_id: str,
        original_filename: str,
        source_stream: BinaryIO,
        max_bytes: int,
    ) -> NotePaths:
        return self.storage.write_uploaded_file_note(
            username=user.username,
            folder=folder.path,
            title=title,
            filename=note_id,
            original_filename=original_filename,
            source_stream=source_stream,
            max_bytes=max_bytes,
        )

    def create_url_note_placeholder(
        self,
        *,
        user: User,
        folder: Folder,
        title: str,
        note_id: str,
        url: str,
        source_extension: str,
    ) -> NotePaths:
        return self.storage.write_url_note_placeholder(
            username=user.username,
            folder=folder.path,
            title=title,
            filename=note_id,
            url=url,
            source_extension=source_extension,
        )

    def note_path(self, note: Note) -> Path:
        return self.paths.note_file_path(note)

    def stage_move_to_folder(
        self,
        note: Note,
        folder: Folder,
        filesystem: FilesystemUnitOfWork,
    ) -> None:
        move_note_to_folder(
            note,
            folder,
            data_dir=self.paths.data_dir,
            filesystem=filesystem,
        )

    def stage_replace_body(
        self,
        note: Note,
        *,
        title: str,
        text: str,
        filesystem: FilesystemUnitOfWork,
    ) -> None:
        filesystem.replace_text(
            self.note_path(note),
            render_markdown_note(title=title, text=text),
            encoding="utf-8",
        )

    def stage_replace_title(
        self,
        note: Note,
        *,
        title: str,
        filesystem: FilesystemUnitOfWork,
    ) -> None:
        note_path = self.note_path(note)
        filesystem.replace_text(
            note_path,
            replace_markdown_title(note_path.read_text(encoding="utf-8"), title),
            encoding="utf-8",
        )

    def stage_delete(self, note: Note, filesystem: FilesystemUnitOfWork) -> None:
        stage_note_files_for_delete(note, self.paths, filesystem)

    @property
    def workspace_paths(self) -> WorkspacePaths:
        return self.paths
