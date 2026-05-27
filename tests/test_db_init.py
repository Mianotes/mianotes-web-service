from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from mianotes_web_service.db.init import create_database


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
