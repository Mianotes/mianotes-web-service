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


def test_email_check_first_join_regular_join_and_login_flow(client: TestClient):
    first_check = client.post(
        "/api/auth/check-email",
        json={"email": "admin@example.com"},
    )
    assert first_check.status_code == 200
    assert first_check.json() == {
        "user_id": None,
        "is_first_user": True,
        "master_password_owner_name": None,
        "signup_disabled": False,
    }

    setup = client.post(
        "/api/auth/join",
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

    folders = client.get("/api/folders")
    assert folders.status_code == 200
    onboarding_folder = next(
        folder for folder in folders.json() if folder["name"] == "Mianotes"
    )

    notes = client.get("/api/notes", params={"folder_id": onboarding_folder["id"]})
    assert notes.status_code == 200
    onboarding_note = notes.json()[0]
    assert onboarding_note["title"] == "Getting Started"
    assert "Thank you for installing Mianotes" in onboarding_note["summary"]

    note = client.get(f"/api/notes/{onboarding_note['id']}")
    assert note.status_code == 200
    note_payload = note.json()
    note_text = note_payload["text"]
    assert "https://tally.so/r/xXvQbk" in note_text
    assert "![Settings workspace switcher](/markdown/mianotes/sources/" in note_text
    assert "![Workspace switcher](/markdown/mianotes/sources/" in note_text
    source_dir = Path(note_payload["source_files"][0]["file_path"]).parent
    assert (source_dir / "onboarding_settings_workspace_switcher.jpg").is_file()
    assert (source_dir / "onboarding_workspace_switcher.jpg").is_file()

    session = client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["id"] == admin["id"]

    known_check = client.post(
        "/api/auth/check-email",
        json={"email": "admin@example.com"},
    )
    assert known_check.status_code == 200
    assert known_check.json() == {
        "user_id": admin["id"],
        "is_first_user": None,
        "master_password_owner_name": "Admin",
        "signup_disabled": False,
    }

    unknown_check = client.post(
        "/api/auth/check-email",
        json={"email": "maria@example.com"},
    )
    assert unknown_check.status_code == 200
    assert unknown_check.json() == {
        "user_id": None,
        "is_first_user": None,
        "master_password_owner_name": "Admin",
        "signup_disabled": False,
    }

    joined = client.post(
        "/api/auth/join",
        json={
            "email": "maria@example.com",
            "name": "Maria",
            "password": "maria-password",
            "password_confirmation": "maria-password",
        },
    )
    assert joined.status_code == 201
    maria = joined.json()["user"]
    assert maria["is_admin"] is False

    maria_login = client.post(
        "/api/auth/login",
        json={"user_id": maria["id"], "password": "maria-password"},
    )
    assert maria_login.status_code == 200

    logged_in = client.post(
        "/api/auth/login",
        json={"user_id": admin["id"], "password": "house-password"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["id"] == admin["id"]


def test_admin_only_workspace_blocks_new_accounts(client: TestClient):
    setup = client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
            "workspace_access_mode": "admin_only",
        },
    )
    assert setup.status_code == 201
    admin = setup.json()["user"]
    assert admin["is_admin"] is True

    client.post("/api/auth/logout")
    unknown_check = client.post(
        "/api/auth/check-email",
        json={"email": "maria@example.com"},
    )
    assert unknown_check.status_code == 200
    assert unknown_check.json()["signup_disabled"] is True

    blocked = client.post(
        "/api/auth/join",
        json={
            "email": "maria@example.com",
            "name": "Maria",
            "password": "maria-password",
            "password_confirmation": "maria-password",
        },
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "This workspace is limited to the admin account"

    logged_in = client.post(
        "/api/auth/login",
        json={"user_id": admin["id"], "password": "house-password"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["id"] == admin["id"]


def test_open_workspace_requires_new_users_to_choose_password(client: TestClient):
    setup = client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
            "workspace_access_mode": "open",
        },
    )
    assert setup.status_code == 201

    missing_confirmation = client.post(
        "/api/auth/join",
        json={
            "email": "maria@example.com",
            "name": "Maria",
            "password": "maria-password",
        },
    )
    assert missing_confirmation.status_code == 422
    assert missing_confirmation.json()["detail"] == "Password confirmation is required"

    joined = client.post(
        "/api/auth/join",
        json={
            "email": "maria@example.com",
            "name": "Maria",
            "password": "maria-password",
            "password_confirmation": "maria-password",
        },
    )
    assert joined.status_code == 201
    maria = joined.json()["user"]
    client.post("/api/auth/logout")

    old_master_login = client.post(
        "/api/auth/login",
        json={"user_id": maria["id"], "password": "house-password"},
    )
    assert old_master_login.status_code == 401

    logged_in = client.post(
        "/api/auth/login",
        json={"user_id": maria["id"], "password": "maria-password"},
    )
    assert logged_in.status_code == 200
