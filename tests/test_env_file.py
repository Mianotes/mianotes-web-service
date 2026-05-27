from pathlib import Path

from mianotes_web_service.services.env_file import (
    DEFAULT_SERVICE_API_URL,
    ensure_service_api_url,
    read_env_value,
    service_env_file_path,
    upsert_env_value,
)


def test_service_env_file_path_prefers_explicit_env_file(monkeypatch, tmp_path: Path):
    env_file = tmp_path / "mianotes.env"
    fallback = tmp_path / "fallback.env"
    monkeypatch.setenv("MIANOTES_ENV_FILE", str(env_file))
    monkeypatch.setenv("MIANOTES_ENV_FILE_PATH", str(fallback))

    assert service_env_file_path() == env_file


def test_service_env_file_path_uses_legacy_env_file_path(monkeypatch, tmp_path: Path):
    env_file = tmp_path / "legacy.env"
    monkeypatch.delenv("MIANOTES_ENV_FILE", raising=False)
    monkeypatch.setenv("MIANOTES_ENV_FILE_PATH", str(env_file))

    assert service_env_file_path() == env_file


def test_service_env_file_path_defaults_to_project_env(monkeypatch):
    monkeypatch.delenv("MIANOTES_ENV_FILE", raising=False)
    monkeypatch.delenv("MIANOTES_ENV_FILE_PATH", raising=False)

    assert service_env_file_path() == Path(".env")


def test_upsert_env_value_quotes_and_replaces_existing_export(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'export MIANOTES_API_KEY="old"\nOTHER_VALUE=1\nMIANOTES_API_KEY=duplicate\n',
        encoding="utf-8",
    )

    upsert_env_value(env_file, "MIANOTES_API_KEY", 'mia_"quoted"')

    assert env_file.read_text(encoding="utf-8") == (
        'MIANOTES_API_KEY="mia_\\"quoted\\""\n'
        "OTHER_VALUE=1\n"
    )
    assert read_env_value(env_file, "MIANOTES_API_KEY") == 'mia_"quoted"'


def test_ensure_service_api_url_writes_default_when_missing(tmp_path: Path):
    env_file = tmp_path / ".env"

    assert ensure_service_api_url(env_file) == DEFAULT_SERVICE_API_URL
    assert read_env_value(env_file, "MIANOTES_API_URL") == DEFAULT_SERVICE_API_URL


def test_ensure_service_api_url_replaces_localhost_but_preserves_lan_url(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text('MIANOTES_API_URL="http://localhost:8200"\n', encoding="utf-8")

    assert ensure_service_api_url(env_file) == DEFAULT_SERVICE_API_URL
    assert read_env_value(env_file, "MIANOTES_API_URL") == DEFAULT_SERVICE_API_URL

    env_file.write_text('MIANOTES_API_URL="http://192.168.1.10:8200"\n', encoding="utf-8")

    assert ensure_service_api_url(env_file) == "http://192.168.1.10:8200"
    assert read_env_value(env_file, "MIANOTES_API_URL") == "http://192.168.1.10:8200"
