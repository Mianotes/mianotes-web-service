from sqlalchemy import create_engine, inspect
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
