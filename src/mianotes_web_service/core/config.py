from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mianotes Web Service"
    host: str = "127.0.0.1"
    port: int = 8200
    data_dir: Path = Field(default=Path("data"))
    database_url: str = "sqlite:///mianotes.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MIANOTES_",
        extra="ignore",
    )

    @property
    def redacted_database_url(self) -> str:
        if "@" not in self.database_url:
            return self.database_url
        scheme, rest = self.database_url.split("://", 1)
        _, host = rest.rsplit("@", 1)
        return f"{scheme}://***@{host}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
