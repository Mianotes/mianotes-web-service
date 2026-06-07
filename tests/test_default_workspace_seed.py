from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mianotes_web_service.db.models import Base, Note
from mianotes_web_service.services.default_workspace_seed import seed_default_workspace


def test_seed_default_workspace_copies_compatible_markdown_and_imports_note(
    tmp_path: Path,
):
    session = _session()
    try:
        workspace_folder = tmp_path / "workspace"

        imported = seed_default_workspace(
            session,
            workspace_folder=workspace_folder,
            user_id="user-1",
        )
        session.commit()

        seed_note = workspace_folder / "markdown" / "mianotes" / "getting-started-00000001.md"
        note = session.scalars(select(Note)).one()
        assert imported == 1
        assert seed_note.is_file()
        assert note.title == "Getting Started"
        assert note.note_path == str(seed_note)
        assert "Thank you for installing Mianotes" in note.summary
    finally:
        session.close()


def test_seed_default_workspace_skips_non_empty_workspace(tmp_path: Path):
    session = _session()
    try:
        workspace_folder = tmp_path / "workspace"
        assert (
            seed_default_workspace(
                session,
                workspace_folder=workspace_folder,
                user_id="user-1",
            )
            == 1
        )
        session.commit()
        seed_note = workspace_folder / "markdown" / "mianotes" / "getting-started-00000001.md"
        seed_note.write_text("# User edited this file\n", encoding="utf-8")

        imported = seed_default_workspace(
            session,
            workspace_folder=workspace_folder,
            user_id="user-1",
        )

        assert imported == 0
        assert seed_note.read_text(encoding="utf-8") == "# User edited this file\n"
    finally:
        session.close()


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return testing_session()
