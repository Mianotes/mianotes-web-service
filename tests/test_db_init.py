from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db.init import (
    create_database,
    create_system_database,
    create_workspace_database,
)
from mianotes_web_service.db.models import ApiToken, Folder, SessionToken, User
from mianotes_web_service.db.session import create_database_engine
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

    tables = set(inspect(engine).get_table_names())

    assert "users" in tables
    assert "notes" in tables
    assert "mia_jobs" in tables


def test_system_and_workspace_databases_have_separate_tables(tmp_path):
    system_engine = create_database_engine(f"sqlite:///{tmp_path / 'system.db'}")
    workspace_engine = create_database_engine(
        f"sqlite:///{tmp_path / 'workspace' / '.mianotes' / 'mia.db'}"
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
        f"sqlite:///{tmp_path / 'workspace' / '.mianotes' / 'mia.db'}"
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
        database_file=".mianotes/mia.db",
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


def test_create_database_adds_password_hash_to_existing_users_table():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id VARCHAR(36) PRIMARY KEY,
                    email VARCHAR(320) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    username VARCHAR(64) NOT NULL,
                    is_admin BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )

    create_database(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "password_hash" in columns


def test_create_database_adds_agent_client_columns_to_existing_jobs_table():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id VARCHAR(36) PRIMARY KEY,
                    email VARCHAR(320) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    username VARCHAR(64) NOT NULL,
                    is_admin BOOLEAN NOT NULL,
                    password_hash TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE mia_jobs (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    note_id VARCHAR(36),
                    job_type VARCHAR(80) NOT NULL,
                    status VARCHAR(40) NOT NULL,
                    input_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    log_json TEXT NOT NULL,
                    error TEXT,
                    started_at DATETIME,
                    finished_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )

    create_database(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("mia_jobs")}
    assert "client_key" in columns
    assert "client_name" in columns
