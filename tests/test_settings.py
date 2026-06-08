from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from mianotes_web_service.core.config import Settings, get_settings
from mianotes_web_service.db.engine import create_database_engine
from mianotes_web_service.db.workspace_routing import system_database_url
from mianotes_web_service.services import mia, runtime_env
from mianotes_web_service.services.ai_provider_settings import (
    AiProviderConnectionError,
    connect_ai_provider,
    read_ai_provider_settings,
    save_ai_provider_settings,
)


@pytest.fixture(autouse=True)
def isolate_runtime_env_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_env.sys, "prefix", str(tmp_path / "python"))
    monkeypatch.setattr(runtime_env, "PACKAGED_ENV_FILES", ())
    for key in (
        "MIANOTES_LLM_PROVIDER",
        "MIANOTES_LLM_MODEL",
        "MIANOTES_LLM_BASE_URL",
        "MIANOTES_LLM_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_settings_json_supplies_server_llm_vlm_and_binaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    for key in (
        "MIANOTES_HOST",
        "MIANOTES_PORT",
        "MIANOTES_LLM_PROVIDER",
        "MIANOTES_LLM_MODEL",
        "MIANOTES_LLM_BASE_URL",
        "MIANOTES_VLM_PROVIDER",
        "MIANOTES_VLM_MODEL",
        "MIANOTES_VLM_BASE_URL",
        "MIANOTES_ENV_FILE",
        "MIANOTES_ENV_FILE_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MIANOTES_LLM_API_KEY", "sk-llm")
    monkeypatch.setenv("MIANOTES_VLM_API_KEY", "sk-vlm")
    write_json(
        tmp_path / "settings.json",
        {
            "server": {"host": "0.0.0.0", "port": 8300},
            "llm": {
                "provider": "openai-compatible",
                "model": "team-model",
                "baseUrl": "https://llm.example.test/v1",
                "apiKey": "env.MIANOTES_LLM_API_KEY",
            },
            "vlm": {
                "provider": "openai",
                "model": "vision-model",
                "baseUrl": "",
                "apiKey": "env.MIANOTES_VLM_API_KEY",
            },
            "binaries": {"ffmpeg": ["/custom/bin/ffmpeg"]},
        },
    )

    settings = Settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 8300
    assert settings.llm_provider == "openai-compatible"
    assert settings.llm_model == "team-model"
    assert settings.llm_base_url == "https://llm.example.test/v1"
    assert settings.llm_api_key == "sk-llm"
    assert settings.vlm_provider == "openai"
    assert settings.vlm_model == "vision-model"
    assert settings.vlm_api_key == "sk-vlm"
    assert settings.binaries == {"ffmpeg": ["/custom/bin/ffmpeg"]}


def test_environment_values_override_settings_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MIANOTES_PORT", "8400")
    write_json(tmp_path / "settings.json", {"server": {"port": 8300}})

    settings = Settings()

    assert settings.port == 8400


def test_settings_json_secret_reference_can_read_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("MIANOTES_LLM_API_KEY=sk-dotenv\n", encoding="utf-8")
    write_json(
        tmp_path / "settings.json",
        {"llm": {"apiKey": "env.MIANOTES_LLM_API_KEY"}},
    )

    settings = Settings()

    assert settings.llm_api_key == "sk-dotenv"


def test_dotenv_shell_reference_can_read_dotenv_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-openai\n"
        "MIANOTES_LLM_API_KEY=$OPENAI_API_KEY\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.llm_api_key == "sk-openai"


def test_dotenv_shell_reference_can_read_process_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-process")
    (tmp_path / ".env").write_text(
        "MIANOTES_LLM_API_KEY=${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.llm_api_key == "sk-process"


def test_configured_service_env_file_supplies_llm_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / "mianotes.env"
    env_file.write_text(
        "OPENAI_API_KEY=sk-service\n"
        "MIANOTES_LLM_PROVIDER=openai\n"
        "MIANOTES_LLM_MODEL=gpt-5-nano\n"
        "MIANOTES_LLM_API_KEY=$OPENAI_API_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MIANOTES_ENV_FILE", str(env_file))

    settings = Settings()

    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-5-nano"
    assert settings.llm_api_key == "sk-service"


def test_configured_service_env_file_overrides_settings_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / "mianotes.env"
    env_file.write_text("MIANOTES_LLM_MODEL=service-model\n", encoding="utf-8")
    write_json(tmp_path / "settings.json", {"llm": {"model": "settings-model"}})
    monkeypatch.setenv("MIANOTES_ENV_FILE", str(env_file))

    settings = Settings()

    assert settings.llm_model == "service-model"


def test_settings_do_not_read_packaged_env_without_explicit_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    packaged_env = tmp_path / "packaged" / "mianotes.env"
    packaged_env.parent.mkdir()
    packaged_env.write_text("MIANOTES_LLM_MODEL=packaged-model\n", encoding="utf-8")
    monkeypatch.setattr(runtime_env, "PACKAGED_ENV_FILES", (packaged_env,))
    monkeypatch.delenv("MIANOTES_ENV_FILE", raising=False)
    monkeypatch.delenv("MIANOTES_ENV_FILE_PATH", raising=False)

    settings = Settings()

    assert settings.llm_model is None


def test_unsupported_database_adapter_fails_clearly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "MIANOTES_DATABASE_URL",
        "postgresql+psycopg://mianotes@example.test/mianotes",
    )
    write_json(
        tmp_path / "settings.json",
        {
            "database": {
                "adapter": "postgresql",
                "url": "env.MIANOTES_DATABASE_URL",
            }
        },
    )

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "Database adapter 'postgresql' is not supported yet" in str(exc_info.value)


def test_system_database_url_uses_configured_sqlite_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "configured-system.db"
    monkeypatch.setenv("MIANOTES_DATABASE_URL", f"sqlite:///{database_path}")
    get_settings.cache_clear()

    assert system_database_url() == f"sqlite:///{database_path}"


def test_file_sqlite_databases_enable_wal(tmp_path: Path) -> None:
    database_path = tmp_path / "wal" / "system.db"
    engine = create_database_engine(f"sqlite:///{database_path}")

    with engine.connect() as connection:
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()

    assert journal_mode == "wal"


def test_save_ai_provider_settings_writes_service_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / "mianotes.env"
    monkeypatch.setenv("MIANOTES_ENV_FILE", str(env_file))
    get_settings.cache_clear()

    settings = save_ai_provider_settings(
        provider="openai-compatible",
        model="team-model",
        base_url="https://llm.example.test/v1",
    )

    assert settings.provider == "openai-compatible"
    assert settings.model == "team-model"
    assert settings.base_url == "https://llm.example.test/v1"
    assert settings.has_api_key is False
    env_text = env_file.read_text(encoding="utf-8")
    assert 'MIANOTES_LLM_PROVIDER="openai-compatible"' in env_text
    assert 'MIANOTES_LLM_MODEL="team-model"' in env_text
    assert 'MIANOTES_LLM_BASE_URL="https://llm.example.test/v1"' in env_text
    assert "MIANOTES_LLM_API_KEY" not in env_text
    get_settings.cache_clear()


def test_connect_ai_provider_tests_before_writing_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            calls["completion"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / "mianotes.env"
    monkeypatch.setenv("MIANOTES_ENV_FILE", str(env_file))
    monkeypatch.setattr(mia, "OpenAI", FakeOpenAI)
    get_settings.cache_clear()

    settings = connect_ai_provider(
        provider="openai",
        model="gpt-5-nano",
        base_url="",
        api_key="sk-test",
    )

    assert settings.provider == "openai"
    assert settings.model == "gpt-5-nano"
    assert settings.has_api_key is True
    assert calls["client"] == {"api_key": "sk-test"}
    assert calls["completion"]["model"] == "gpt-5-nano"
    assert read_ai_provider_settings().has_api_key is True
    env_text = env_file.read_text(encoding="utf-8")
    assert 'MIANOTES_LLM_API_KEY="sk-test"' in env_text
    get_settings.cache_clear()


def test_connect_ai_provider_does_not_save_api_key_when_test_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompletions:
        def create(self, **kwargs):
            raise RuntimeError("bad key")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / "mianotes.env"
    monkeypatch.setenv("MIANOTES_ENV_FILE", str(env_file))
    monkeypatch.setattr(mia, "OpenAI", FakeOpenAI)
    get_settings.cache_clear()

    with pytest.raises(AiProviderConnectionError):
        connect_ai_provider(
            provider="openai",
            model="gpt-5-nano",
            base_url="",
            api_key="sk-test",
        )

    assert not env_file.exists()
    get_settings.cache_clear()
