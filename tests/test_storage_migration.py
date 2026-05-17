from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db.models import Base, Note, Project, SourceFile, User
from mianotes_web_service.services.storage import make_username
from mianotes_web_service.services.storage_migration import migrate_readable_storage_paths


def test_migrate_readable_storage_paths_moves_existing_files(tmp_path: Path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    data_dir = tmp_path / "data"
    old_username = make_username("note@example.com")
    old_dir = data_dir / old_username / "mallorca-trip"
    old_dir.mkdir(parents=True)
    note_id = "4a95f146-9d27-4c79-b7d8-34739aef8998"
    old_note_path = old_dir / f"{note_id}.md"
    old_source_path = old_dir / f"{note_id}.source.txt"
    old_note_path.write_text("# Planning Trip to Mallorca\n", encoding="utf-8")
    old_source_path.write_text("raw text", encoding="utf-8")

    user = User(
        id="user-1",
        email="note@example.com",
        name="Mia Agent",
        username=old_username,
        is_admin=True,
    )
    project = Project(
        id="project-1",
        user_id=user.id,
        name="Mallorca Trip",
        slug="mallorca-trip",
    )
    note = Note(
        id=note_id,
        user_id=user.id,
        project_id=project.id,
        title="Planning Trip to Mallorca",
        note_path=str(old_note_path),
    )
    source_file = SourceFile(
        id="source-1",
        note_id=note.id,
        file_path=str(old_source_path),
        original_filename="planning.txt",
        content_type="text/plain",
    )
    session.add_all([user, project, note, source_file])
    session.commit()

    result = migrate_readable_storage_paths(session, data_dir=data_dir)

    expected_dir = data_dir / "mia-agent-926c16ee" / "mallorca-trip"
    expected_stem = "planning-trip-to-mallorca-4a95f146"
    expected_note_path = expected_dir / f"{expected_stem}.md"
    expected_source_path = expected_dir / f"{expected_stem}.source.txt"

    session.refresh(user)
    session.refresh(note)
    session.refresh(source_file)

    assert result.users_updated == 1
    assert result.notes_updated == 1
    assert result.source_files_updated == 1
    assert result.files_moved == 2
    assert user.username == "mia-agent-926c16ee"
    assert note.note_path == str(expected_note_path)
    assert source_file.file_path == str(expected_source_path)
    assert expected_note_path.read_text(encoding="utf-8") == "# Planning Trip to Mallorca\n"
    assert expected_source_path.read_text(encoding="utf-8") == "raw text"
    assert not old_note_path.exists()
    assert not old_source_path.exists()
