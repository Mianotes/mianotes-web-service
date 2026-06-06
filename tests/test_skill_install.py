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
from mianotes_web_service.services.skill_installer import INSTALL_CODE_HOURS, hash_install_code


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
    app.state.testing_session_factory = testing_session
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
    started_at = datetime.now(UTC)

    response = client.post(
        "/api/install/skill",
        json={"api_url": "http://mianotes.local:8200/", "client_name": "Codex"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["install_url"].startswith("http://mianotes.local:8200/skill/install.sh?code=")
    assert payload["command"].startswith('curl -fsSL "')
    assert payload["command"].endswith(" | bash")
    assert "mia_" not in payload["command"]
    expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    expected_expires_at = started_at + timedelta(hours=INSTALL_CODE_HOURS)
    assert (
        expected_expires_at - timedelta(seconds=5)
        <= expires_at
        <= expected_expires_at + timedelta(seconds=5)
    )


def test_skill_installer_redeems_once_and_installs_user_token(client: TestClient):
    user = _join_user(client)
    install = client.post(
        "/api/install/skill",
        json={"api_url": "http://mianotes.local:8200", "client_name": "Codex"},
    ).json()
    code = _code_from_install_url(install["install_url"])

    script_response = client.get(f"/skill/install.sh?code={code}")

    assert script_response.status_code == 200
    script = script_response.text
    assert "MIANOTES_API_KEY=mia_" not in script
    assert "curl -fsSL 'http://mianotes.local:8200/skill/install.env?code=" in script
    assert 'mv "${TMP_ENV}" "${MIANOTES_ENV_FILE}"' in script
    assert ".codex/skills/mianotes/SKILL.md" in script
    assert ".claude/skills/mianotes/SKILL.md" in script
    assert 'Added environment variables for API access.' in script
    assert '     |_  ~/.mianotes/env' in script
    assert 'Installed SKILL.md for Claude Code and Codex.' in script
    assert '     |_ ~/.codex/skills/mianotes/SKILL.md' in script
    assert '     |_ ~/.claude/skills/mianotes/SKILL.md' in script
    assert "Mia is the local Mianotes knowledge service." in script

    env_response = client.get(f"/skill/install.env?code={code}")
    assert env_response.status_code == 200
    env_file = env_response.text
    assert "MIANOTES_API_URL=http://mianotes.local:8200" in env_file
    assert "MIANOTES_API_USER=fedecarg@gmail.com" in env_file
    assert "MIANOTES_API_KEY=mia_" in env_file

    second_response = client.get(f"/skill/install.env?code={code}")
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
    env_file = client.get(f"/skill/install.env?code={code}").text
    api_key_line = next(
        line
        for line in env_file.splitlines()
        if line.startswith("export MIANOTES_API_KEY=")
    )
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

    response = client.get("/skill/install.sh?code=expired-code")

    assert response.status_code == 410
    assert response.json()["detail"] == "Install code has expired"


@pytest.mark.parametrize(
    "api_url",
    [
        "https://notes.example.com",
        "http://mianotes.local:8200",
        "http://localhost:8200",
        "http://127.0.0.1:8200",
        "http://10.1.2.3:8200",
        "http://172.16.0.10:8200",
        "http://172.31.255.254:8200",
        "http://192.168.1.20:8200",
        "http://169.254.1.20:8200",
    ],
)
def test_skill_installer_allows_https_and_local_private_exchange_hosts(
    client: TestClient,
    api_url: str,
):
    _join_user(client)

    response = client.post(
        "/api/install/skill",
        json={"api_url": api_url, "client_name": "Codex"},
    )

    assert response.status_code == 201


def test_skill_installer_rejects_public_http_exchange_hosts(client: TestClient):
    _join_user(client)

    response = client.post(
        "/api/install/skill",
        json={"api_url": "http://example.com:8200", "client_name": "Codex"},
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Mianotes API URL must use HTTPS or a trusted local/private address"
    )
