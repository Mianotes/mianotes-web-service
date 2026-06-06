from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db.models import Base, Folder, Note, SourceFile, User, new_id
from mianotes_web_service.services.filesystem_uow import FilesystemUnitOfWork
from mianotes_web_service.services.note_files import NoteFiles
from mianotes_web_service.services.workspace_context import WorkspaceContext


def _session_for_workspace(tmp_path: Path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    session.info["workspace"] = WorkspaceContext(
        id="docs",
        name="Docs",
        folder_path=tmp_path / "workspace",
    )
    return session


def _user_and_folder(session):
    user = User(
        id=new_id(),
        email="notes@example.com",
        name="Notes User",
        username="notes-user",
    )
    folder = Folder(
        id=new_id(),
        user_id=user.id,
        name="Research",
        slug="research",
        path="research",
    )
    session.add_all([user, folder])
    session.commit()
    return user, folder


def test_note_files_creates_text_note_in_workspace(tmp_path: Path):
    session = _session_for_workspace(tmp_path)
    user, folder = _user_and_folder(session)
    note_id = new_id()

    paths = NoteFiles(session).create_text_note(
        user=user,
        folder=folder,
        title="OCR Plan",
        text="Try local OCR first.",
        note_id=note_id,
    )

    assert paths.note_path == tmp_path / "workspace" / "markdown" / "research" / (
        f"ocr-plan-{note_id[:8]}.md"
    )
    assert paths.note_path.read_text(encoding="utf-8").startswith("# OCR Plan")
    assert paths.source_path is not None
    assert paths.source_path.read_text(encoding="utf-8") == "Try local OCR first."


def test_note_files_stages_title_and_body_replacements(tmp_path: Path):
    session = _session_for_workspace(tmp_path)
    user, folder = _user_and_folder(session)
    note_id = new_id()
    paths = NoteFiles(session).create_text_note(
        user=user,
        folder=folder,
        title="Original",
        text="Original body.",
        note_id=note_id,
    )
    note = Note(
        id=note_id,
        user_id=user.id,
        folder_id=folder.id,
        folder=folder,
        title="Original",
        filename=paths.note_path.name,
        note_path=str(paths.note_path),
    )
    session.add(note)
    session.commit()

    filesystem = FilesystemUnitOfWork()
    note_files = NoteFiles(session)
    note_files.stage_replace_title(note, title="Renamed", filesystem=filesystem)
    assert paths.note_path.read_text(encoding="utf-8").startswith("# Renamed")
    filesystem.rollback()
    assert paths.note_path.read_text(encoding="utf-8").startswith("# Original")

    filesystem = FilesystemUnitOfWork()
    note_files.stage_replace_body(
        note,
        title="Original",
        text="Replacement body.",
        filesystem=filesystem,
    )
    assert "Replacement body." in paths.note_path.read_text(encoding="utf-8")
    filesystem.rollback()
    assert "Original body." in paths.note_path.read_text(encoding="utf-8")


def test_note_files_stages_delete_and_can_roll_back(tmp_path: Path):
    session = _session_for_workspace(tmp_path)
    user, folder = _user_and_folder(session)
    note_id = new_id()
    paths = NoteFiles(session).create_text_note(
        user=user,
        folder=folder,
        title="Delete me",
        text="Temporary body.",
        note_id=note_id,
    )
    note = Note(
        id=note_id,
        user_id=user.id,
        folder_id=folder.id,
        folder=folder,
        title="Delete me",
        filename=paths.note_path.name,
        note_path=str(paths.note_path),
    )
    source_file = SourceFile(
        note=note,
        filename=str(paths.source_path.relative_to(paths.directory)),
        file_path=str(paths.source_path),
        original_filename="original.txt",
        content_type="text/plain",
    )
    image_directory = paths.directory / "images" / note_id[:8]
    image_directory.mkdir(parents=True)
    image_path = image_directory / "diagram.png"
    image_path.write_bytes(b"fake image")
    session.add_all([note, source_file])
    session.commit()

    filesystem = FilesystemUnitOfWork()
    NoteFiles(session).stage_delete(note, filesystem)

    assert not paths.note_path.exists()
    assert paths.source_path is not None
    assert not paths.source_path.exists()
    assert not image_path.exists()

    filesystem.rollback()

    assert paths.note_path.exists()
    assert paths.source_path.exists()
    assert image_path.exists()
