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
