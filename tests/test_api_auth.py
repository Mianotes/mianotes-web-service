from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Base
from mianotes_web_service.db.session import get_session


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("MIANOTES_DATA_DIR", str(tmp_path / "data"))
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_session() -> Generator[Session, None, None]:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_email_check_setup_join_and_login_flow(client: TestClient):
    first_check = client.post(
        "/api/auth/check-email",
        json={"email": "admin@example.com"},
    )
    assert first_check.status_code == 200
    assert first_check.json() == {"user_id": None, "is_first_user": True}

    setup = client.post(
        "/api/auth/setup-admin",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    assert setup.status_code == 201
    admin = setup.json()["user"]
    assert admin["is_admin"] is True

    session = client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["id"] == admin["id"]

    known_check = client.post(
        "/api/auth/check-email",
        json={"email": "admin@example.com"},
    )
    assert known_check.status_code == 200
    assert known_check.json() == {"user_id": admin["id"]}

    unknown_check = client.post(
        "/api/auth/check-email",
        json={"email": "maria@example.com"},
    )
    assert unknown_check.status_code == 200
    assert unknown_check.json() == {"user_id": None}

    joined = client.post(
        "/api/auth/join",
        json={
            "email": "maria@example.com",
            "name": "Maria",
            "password": "house-password",
        },
    )
    assert joined.status_code == 201
    maria = joined.json()["user"]
    assert maria["is_admin"] is False

    logged_in = client.post(
        "/api/auth/login",
        json={"user_id": admin["id"], "password": "house-password"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["id"] == admin["id"]
