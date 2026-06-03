from contextvars import copy_context

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db import session as db_session
from mianotes_web_service.db.engine import create_database_engine
from mianotes_web_service.db.init import (
    create_database,
    create_system_database,
    create_workspace_database,
)
from mianotes_web_service.db.models import ApiToken, Folder, SessionToken, User
from mianotes_web_service.services.auth import create_session_token
from mianotes_web_service.services.workspace_context import (
    WorkspaceContext,
    reset_current_workspace,
    set_current_workspace,
)


def test_create_database_uses_current_model_schema():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    create_database(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("mia_jobs")}
    assert "log_json" in columns
    indexes = {index["name"] for index in inspect(engine).get_indexes("notes")}
    assert "ix_notes_folder_title" in indexes
    assert "ix_notes_folder_updated_at" in indexes

    tables = set(inspect(engine).get_table_names())

    assert "users" in tables
    assert "notes" in tables
    assert "mia_jobs" in tables


def test_system_and_workspace_databases_have_separate_tables(tmp_path):
    system_engine = create_database_engine(f"sqlite:///{tmp_path / 'system.db'}")
    workspace_engine = create_database_engine(
        f"sqlite:///{tmp_path / 'workspaces' / 'workspace.db'}"
    )

    create_system_database(system_engine)
    create_workspace_database(workspace_engine)

    system_tables = set(inspect(system_engine).get_table_names())
    workspace_tables = set(inspect(workspace_engine).get_table_names())

    assert {"users", "session_tokens", "api_tokens", "app_settings"} <= system_tables
    assert "notes" not in system_tables
    assert "folders" not in system_tables

    assert {"folders", "notes", "mia_jobs", "source_files"} <= workspace_tables
    assert "users" not in workspace_tables
    assert "session_tokens" not in workspace_tables

    session_columns = {
        column["name"] for column in inspect(system_engine).get_columns("session_tokens")
    }
    assert "workspace_id" in session_columns


def test_session_factory_routes_global_models_to_system_database(tmp_path):
    system_engine = create_database_engine(f"sqlite:///{tmp_path / 'system.db'}")
    workspace_engine = create_database_engine(
        f"sqlite:///{tmp_path / 'workspaces' / 'workspace.db'}"
    )
    create_system_database(system_engine)
    create_workspace_database(workspace_engine)
    SessionLocal = sessionmaker(
        bind=workspace_engine,
        binds={model: system_engine for model in (User, SessionToken, ApiToken)},
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    with SessionLocal() as session:
        user = User(email="admin@example.com", name="Admin", username="admin", is_admin=True)
        session.add(user)
        session.flush()
        folder = Folder(user_id=user.id, name="Docs", slug="docs", path="docs")
        session.add(folder)
        session.commit()

    with system_engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 1

    with workspace_engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM folders")).scalar_one() == 1


def test_session_token_records_current_workspace(tmp_path):
    system_engine = create_database_engine(f"sqlite:///{tmp_path / 'system.db'}")
    create_system_database(system_engine)
    SessionLocal = sessionmaker(
        bind=system_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    workspace = WorkspaceContext(
        id="research",
        name="Research",
        folder_path=tmp_path / "research",
    )

    with SessionLocal() as session:
        user = User(email="admin@example.com", name="Admin", username="admin", is_admin=True)
        session.add(user)
        session.commit()

        token = set_current_workspace(workspace)
        try:
            session_token = create_session_token(session, user)
        finally:
            reset_current_workspace(token)
        session.commit()

        stored_token = session.get(SessionToken, session_token.id)
        assert stored_token is not None
        assert stored_token.workspace_id == "research"


def test_reset_current_workspace_tolerates_different_context(tmp_path):
    workspace = WorkspaceContext(
        id="research",
        name="Research",
        folder_path=tmp_path / "research",
    )
    token = copy_context().run(set_current_workspace, workspace)

    reset_current_workspace(token)


def test_get_session_cleanup_tolerates_different_context(tmp_path, monkeypatch):
    workspace = WorkspaceContext(
        id="research",
        name="Research",
        folder_path=tmp_path / "research",
    )
    engine = create_database_engine(f"sqlite:///{tmp_path / 'workspaces' / 'research.db'}")
    create_workspace_database(engine)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(db_session, "resolve_workspace", lambda **_kwargs: workspace)
    monkeypatch.setattr(db_session, "sessionmaker_for_workspace", lambda _workspace: SessionLocal)

    session_dependency = db_session.get_session(object())
    opened_session = copy_context().run(lambda: next(session_dependency))

    assert opened_session.info["workspace"] == workspace
    session_dependency.close()
