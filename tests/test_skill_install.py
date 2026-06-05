from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import ApiToken, Base, SkillInstallCode
from mianotes_web_service.db.session import get_session
from mianotes_web_service.services.skill_installer import hash_install_code


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("MIANOTES_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MIANOTES_STORAGE_CONFIG_PATH", str(tmp_path / "workspaces.json"))
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


def _join_user(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/auth/join",
        json={
            "email": "fedecarg@gmail.com",
            "name": "Federico",
            "password": "mia",
            "password_confirmation": "mia",
        },
    )
    assert response.status_code == 201
    return response.json()["user"]


@contextmanager
def _session(client: TestClient) -> Iterator[Session]:
    session_gen = client.app.dependency_overrides[get_session]()
    session = next(session_gen)
    try:
        yield session
    finally:
        session_gen.close()


def _code_from_install_url(install_url: str) -> str:
    parsed = urlparse(install_url)
    return parse_qs(parsed.query)["code"][0]


def test_signed_in_user_can_create_one_time_skill_installer(client: TestClient):
    _join_user(client)

    response = client.post(
        "/api/install/skill",
        json={"api_url": "http://mianotes.local:8200/", "client_name": "Codex"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["install_url"].startswith("http://mianotes.local:8200/install/skill.sh?code=")
    assert payload["command"].startswith("curl -fsSL ")
    assert payload["command"].endswith(" | bash")
    assert "mia_" not in payload["command"]


def test_skill_installer_redeems_once_and_installs_user_token(client: TestClient):
    user = _join_user(client)
    install = client.post(
        "/api/install/skill",
        json={"api_url": "http://mianotes.local:8200", "client_name": "Codex"},
    ).json()
    code = _code_from_install_url(install["install_url"])

    script_response = client.get(f"/install/skill.sh?code={code}")

    assert script_response.status_code == 200
    script = script_response.text
    assert "MIANOTES_API_URL=http://mianotes.local:8200" in script
    assert "MIANOTES_API_USER=fedecarg@gmail.com" in script
    assert "MIANOTES_API_KEY=mia_" in script
    assert ".codex/skills/mianotes/SKILL.md" in script
    assert ".claude/skills/mianotes/SKILL.md" in script
    assert "Mia is the local Mianotes knowledge service." in script

    second_response = client.get(f"/install/skill.sh?code={code}")
    assert second_response.status_code == 410

    with _session(client) as session:
        tokens = session.scalars(select(ApiToken).where(ApiToken.user_id == user["id"])).all()
        assert len(tokens) == 1
        assert tokens[0].name == "Mianotes API"


def test_skill_installer_token_can_create_agent_session(client: TestClient):
    _join_user(client)
    install = client.post(
        "/api/install/skill",
        json={"api_url": "http://mianotes.local:8200", "client_name": "Codex"},
    ).json()
    code = _code_from_install_url(install["install_url"])
    script = client.get(f"/install/skill.sh?code={code}").text
    api_key_line = next(line for line in script.splitlines() if line.startswith("export MIANOTES_API_KEY="))
    api_key = api_key_line.partition("=")[2]

    session_response = client.post(
        "/api/auth/agent-session",
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Mianotes-Client": "Codex",
        },
    )

    assert session_response.status_code == 201
    assert session_response.json()["user"]["email"] == "fedecarg@gmail.com"


def test_expired_skill_install_code_is_rejected(client: TestClient):
    user = _join_user(client)
    with _session(client) as session:
        code = "expired-code"
        session.add(
            SkillInstallCode(
                user_id=user["id"],
                code_hash=hash_install_code(code),
                api_url="http://mianotes.local:8200",
                client_name="Codex",
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        session.commit()

    response = client.get("/install/skill.sh?code=expired-code")

    assert response.status_code == 410
    assert response.json()["detail"] == "Install code has expired"
