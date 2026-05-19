from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mianotes Web Service"
    host: str = "127.0.0.1"
    port: int = 8200
    data_dir: Path = Field(default=Path("data"))
    database_url: str | None = None
    llm_provider: str = "openai"
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MIANOTES_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def set_default_database_url(self) -> Settings:
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'mia.db'}"
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
