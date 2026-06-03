from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db.models import Base, Folder, MiaJob, Note, NoteTag, PublishedSite, Tag, User


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as session:
        _seed_workspace(session)
    return factory


def _seed_workspace(session: Session) -> None:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    users = [
        User(id="user-1", email="one@example.com", name="One", username="one"),
        User(id="user-2", email="two@example.com", name="Two", username="two"),
    ]
    folders = [
        Folder(id="folder-1", user_id="user-1", name="Docs", slug="docs", path="docs"),
        Folder(id="folder-2", user_id="user-1", name="API", slug="api", path="api"),
    ]
    tags = [
        Tag(id="tag-1", name="Python", slug="python"),
        Tag(id="tag-2", name="Release", slug="release"),
    ]
    session.add_all([*users, *folders, *tags])
    session.flush()

    notes: list[Note] = []
    note_tags: list[NoteTag] = []
    jobs: list[MiaJob] = []
    for index in range(60):
        folder = folders[index % len(folders)]
        user = users[index % len(users)]
        note = Note(
            id=f"note-{index:02d}",
            user_id=user.id,
            folder_id=folder.id,
            title=f"Note {index:02d}",
            status="ready" if index % 4 else "published",
            is_published=index % 3 == 0,
            filename=f"note-{index:02d}.md",
            note_path=f"/tmp/notes/note-{index:02d}.md",
            created_at=created_at + timedelta(minutes=index),
            updated_at=created_at + timedelta(minutes=index),
        )
        notes.append(note)
        if index % 2 == 0:
            note_tags.append(NoteTag(note_id=note.id, tag_id="tag-1"))
        if index % 5 == 0:
            note_tags.append(NoteTag(note_id=note.id, tag_id="tag-2"))
        jobs.append(
            MiaJob(
                id=f"job-{index:02d}",
                user_id=user.id,
                note_id=note.id,
                job_type="parse_file",
                status="failed" if index % 4 == 0 else "queued",
                created_at=created_at + timedelta(minutes=index),
                updated_at=created_at + timedelta(minutes=index),
            )
        )

    session.add_all(notes)
    session.flush()
    session.add_all(note_tags)
    session.add_all(jobs)
    for index in range(12):
        session.add(
            PublishedSite(
                id=f"site-{index:02d}",
                user_id="user-1",
                folder_id="folder-1" if index % 2 == 0 else None,
                tag_id="tag-1" if index % 3 == 0 else None,
                theme="mialight",
                version=f"0.{index}.0",
                html_path=f"/tmp/html/0.{index}.0",
                markdown_path=f"/tmp/markdown/0.{index}.0",
                url_path=f"/0.{index}.0/index.html",
                created_at=created_at + timedelta(hours=index),
                updated_at=created_at + timedelta(hours=index),
            )
        )
    session.commit()


def _explain(session: Session, statement) -> list[str]:
    compiled = statement.compile(
        bind=session.get_bind(),
        compile_kwargs={"literal_binds": True},
    )
    rows = session.execute(text(f"EXPLAIN QUERY PLAN {compiled}")).all()
    return [str(row[-1]) for row in rows]


def _assert_uses_index(plan: list[str], index_name: str) -> None:
    assert any(index_name in row for row in plan), "\n".join(plan)


def _assert_no_temp_sort(plan: list[str]) -> None:
    assert not any("USE TEMP B-TREE" in row and "ORDER BY" in row for row in plan), "\n".join(plan)


def test_note_list_queries_use_composite_indexes(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        default_plan = _explain(
            session,
            select(Note.id).order_by(Note.created_at.desc(), Note.id.desc()).limit(20),
        )
        folder_plan = _explain(
            session,
            select(Note.id)
            .where(Note.folder_id == "folder-1")
            .order_by(Note.created_at.desc(), Note.id.desc())
            .limit(20),
        )
        user_plan = _explain(
            session,
            select(Note.id)
            .where(Note.user_id == "user-1")
            .order_by(Note.created_at.desc(), Note.id.desc())
            .limit(20),
        )

    _assert_uses_index(default_plan, "ix_notes_created_id")
    _assert_uses_index(folder_plan, "ix_notes_folder_created_id")
    _assert_uses_index(user_plan, "ix_notes_user_created_id")
    _assert_no_temp_sort(default_plan)
    _assert_no_temp_sort(folder_plan)
    _assert_no_temp_sort(user_plan)


def test_tag_and_published_file_queries_use_lookup_indexes(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        tag_plan = _explain(
            session,
            select(NoteTag.note_id).where(NoteTag.tag_id == "tag-1").limit(20),
        )
        published_file_plan = _explain(
            session,
            select(Note.id)
            .join(Folder)
            .where(
                Note.is_published.is_(True),
                Note.filename == "note-00.md",
                Folder.path == "docs",
            )
            .limit(1),
        )
        import_lookup_plan = _explain(
            session,
            select(Note.id)
            .where(Note.folder_id == "folder-1", Note.filename == "note-00.md")
            .limit(1),
        )

    _assert_uses_index(tag_plan, "ix_note_tags_tag_note")
    _assert_uses_index(published_file_plan, "ix_notes_published_filename")
    _assert_uses_index(import_lookup_plan, "ix_notes_folder_filename")


def test_publish_history_queries_use_composite_indexes(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        scoped_latest_plan = _explain(
            session,
            select(PublishedSite.id)
            .where(PublishedSite.folder_id == "folder-1", PublishedSite.tag_id.is_(None))
            .order_by(PublishedSite.created_at.desc())
            .limit(1),
        )
        history_plan = _explain(
            session,
            select(PublishedSite.id).order_by(PublishedSite.created_at.desc()).limit(20),
        )

    _assert_uses_index(scoped_latest_plan, "ix_published_sites_scope_created_id")
    _assert_uses_index(history_plan, "ix_published_sites_created_id")
    _assert_no_temp_sort(scoped_latest_plan)
    _assert_no_temp_sort(history_plan)


def test_job_queries_use_composite_indexes(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        user_status_plan = _explain(
            session,
            select(MiaJob.id)
            .where(MiaJob.user_id == "user-1", MiaJob.status == "failed")
            .order_by(MiaJob.created_at.desc(), MiaJob.id.desc())
            .limit(50),
        )
        note_latest_plan = _explain(
            session,
            select(MiaJob.id)
            .where(MiaJob.note_id == "note-00")
            .order_by(MiaJob.created_at.desc(), MiaJob.id.desc())
            .limit(1),
        )

    _assert_uses_index(user_status_plan, "ix_mia_jobs_user_status_created")
    _assert_uses_index(note_latest_plan, "ix_mia_jobs_note_created_id")
    _assert_no_temp_sort(user_status_plan)
    _assert_no_temp_sort(note_latest_plan)
