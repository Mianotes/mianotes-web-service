from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mianotes_web_service.services.storage_settings import (
    ensure_storage_location,
    read_storage_config,
    system_database_path,
)

DEFAULT_BINARY_CANDIDATES: dict[str, list[str]] = {
    "ffmpeg": [
        "ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ],
    "ffprobe": [
        "ffprobe",
        "/opt/homebrew/bin/ffprobe",
        "/usr/local/bin/ffprobe",
        "/usr/bin/ffprobe",
    ],
    "flac": ["flac", "/opt/homebrew/bin/flac", "/usr/local/bin/flac", "/usr/bin/flac"],
    "metaflac": [
        "metaflac",
        "/opt/homebrew/bin/metaflac",
        "/usr/local/bin/metaflac",
        "/usr/bin/metaflac",
    ],
    "tesseract": [
        "tesseract",
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/usr/bin/tesseract",
    ],
}

SUPPORTED_DATABASE_ADAPTERS = {"sqlite"}


def _read_dotenv_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() != key:
            continue
        value = value.strip().strip('"').strip("'")
        return value or None
    return None


def _env_reference_value(reference: object) -> str | None:
    if not isinstance(reference, str) or not reference.startswith("env."):
        return None
    key = reference.removeprefix("env.").strip()
    if not key:
        return None
    return os.environ.get(key) or _read_dotenv_value(Path(".env"), key)


def _settings_json_path(values: dict[str, Any]) -> Path:
    configured = (
        values.get("settings_path")
        or values.get("settingsPath")
        or os.environ.get("MIANOTES_SETTINGS_PATH")
    )
    return Path(str(configured)) if configured else Path("settings.json")


def _load_json_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _flatten_json_settings(payload: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}

    server = payload.get("server")
    if isinstance(server, dict):
        if "host" in server:
            values["host"] = server["host"]
        if "port" in server:
            values["port"] = server["port"]

    database = payload.get("database")
    if isinstance(database, dict):
        if "adapter" in database:
            values["database_adapter"] = database["adapter"]
        database_url = database.get("url")
        if isinstance(database_url, str) and database_url.startswith("env."):
            resolved = _env_reference_value(database_url)
            if resolved:
                values["database_url"] = resolved
        elif database_url:
            values["database_url"] = database_url

    llm = payload.get("llm")
    if isinstance(llm, dict):
        if "provider" in llm:
            values["llm_provider"] = llm["provider"]
        if "model" in llm:
            values["llm_model"] = llm["model"]
        if "baseUrl" in llm:
            values["llm_base_url"] = llm["baseUrl"] or None
        api_key = _env_reference_value(llm.get("apiKey"))
        if api_key:
            values["llm_api_key"] = api_key

    vlm = payload.get("vlm")
    if isinstance(vlm, dict):
        if "provider" in vlm:
            values["vlm_provider"] = vlm["provider"]
        if "model" in vlm:
            values["vlm_model"] = vlm["model"]
        if "baseUrl" in vlm:
            values["vlm_base_url"] = vlm["baseUrl"] or None
        api_key = _env_reference_value(vlm.get("apiKey"))
        if api_key:
            values["vlm_api_key"] = api_key

    binaries = payload.get("binaries")
    if isinstance(binaries, dict):
        values["binaries"] = {
            str(name): [str(candidate) for candidate in candidates]
            for name, candidates in binaries.items()
            if isinstance(candidates, list)
        }

    return values


def _json_settings_defaults(values: dict[str, Any]) -> dict[str, Any]:
    settings_path = _settings_json_path(values)
    flattened = _flatten_json_settings(_load_json_settings(settings_path))
    flattened["settings_path"] = settings_path
    return flattened


def _database_url_adapter(database_url: str | None) -> str | None:
    if not database_url:
        return None
    if database_url.startswith("sqlite"):
        return "sqlite"
    if database_url.startswith("postgresql") or database_url.startswith("postgres"):
        return "postgresql"
    if database_url.startswith("mysql"):
        return "mysql"
    return None


class Settings(BaseSettings):
    app_name: str = "Mianotes Web Service"
    host: str = "127.0.0.1"
    port: int = 8200
    settings_path: Path = Field(default=Path("settings.json"))
    data_dir: Path = Field(default=Path("data"))
    database_adapter: str = "sqlite"
    database_url: str | None = None
    api_key: str | None = None
    api_token: str | None = None
    storage_config_path: Path = Field(default=Path("workspaces.json"))
    llm_provider: str = "openai"
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    vlm_provider: str = "openai"
    vlm_model: str | None = None
    vlm_base_url: str | None = None
    vlm_api_key: str | None = None
    llm_image_model: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-nano"
    binaries: dict[str, list[str]] = Field(default_factory=dict)
    session_cookie_secure: bool = False
    max_upload_bytes: int = 100 * 1024 * 1024
    max_editor_image_bytes: int = 10 * 1024 * 1024
    max_avatar_bytes: int = 5 * 1024 * 1024
    max_image_pixels: int = 50_000_000
    max_url_fetch_bytes: int = 50 * 1024 * 1024
    search_timeout_seconds: float = 5.0
    search_max_file_bytes: int = 2 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MIANOTES_",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def apply_json_settings_defaults(cls, values: object) -> object:
        if values is None:
            values = {}
        if not isinstance(values, dict):
            return values
        defaults = _json_settings_defaults(values)
        return {**defaults, **values}

    @model_validator(mode="after")
    def set_default_database_url(self) -> Settings:
        if not self.api_token:
            self.api_token = self.api_key
        self.database_adapter = self.database_adapter.strip().lower()
        if self.database_adapter not in SUPPORTED_DATABASE_ADAPTERS:
            raise ValueError(
                f"Database adapter '{self.database_adapter}' is not supported yet. "
                "Use 'sqlite' for this release."
            )
        url_adapter = _database_url_adapter(self.database_url)
        if url_adapter and url_adapter != self.database_adapter:
            raise ValueError(
                f"Database URL uses '{url_adapter}' but database adapter is "
                f"'{self.database_adapter}'."
            )
        if not self.database_url:
            storage_config = read_storage_config(
                self.storage_config_path,
                default_data_dir=self.data_dir,
            )
            ensure_storage_location(storage_config.active_folder_path)
            self.database_url = f"sqlite:///{system_database_path(self.data_dir)}"
        return self

    @property
    def redacted_database_url(self) -> str:
        assert self.database_url is not None
        if "@" not in self.database_url:
            return self.database_url
        scheme, rest = self.database_url.split("://", 1)
        _, host = rest.rsplit("@", 1)
        return f"{scheme}://***@{host}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
