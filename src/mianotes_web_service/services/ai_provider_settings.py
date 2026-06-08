from __future__ import annotations

import os
from dataclasses import dataclass

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.services.env_file import service_env_file_path, upsert_env_value
from mianotes_web_service.services.mia import MiaUnavailable, build_llm_config, test_llm_config


class AiProviderConnectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AiProviderSettings:
    provider: str
    model: str | None
    base_url: str | None
    has_api_key: bool


def provider_display_name(provider: str) -> str:
    normalised = provider.strip().lower()
    if normalised == "openai":
        return "OpenAI"
    if normalised in {"local", "ollama"}:
        return "Ollama"
    if normalised in {"compatible", "openai-compatible"}:
        return "OpenAI-compatible provider"
    return provider.strip() or "AI provider"


def read_ai_provider_settings() -> AiProviderSettings:
    settings = get_settings()
    return AiProviderSettings(
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        has_api_key=bool(settings.llm_api_key),
    )


def save_ai_provider_settings(
    *,
    provider: str,
    model: str | None,
    base_url: str | None,
) -> AiProviderSettings:
    _write_ai_provider_env(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=None,
        include_api_key=False,
    )
    return read_ai_provider_settings()


def connect_ai_provider(
    *,
    provider: str,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
) -> AiProviderSettings:
    try:
        config = build_llm_config(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        test_llm_config(config)
    except MiaUnavailable as exc:
        raise AiProviderConnectionError(
            "Unable to connect, check the API key and try again."
        ) from exc

    _write_ai_provider_env(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        include_api_key=True,
    )
    return read_ai_provider_settings()


def _write_ai_provider_env(
    *,
    provider: str,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    include_api_key: bool,
) -> None:
    env_file_path = service_env_file_path()
    values: dict[str, str] = {
        "MIANOTES_LLM_PROVIDER": provider.strip().lower(),
        "MIANOTES_LLM_MODEL": (model or "").strip(),
        "MIANOTES_LLM_BASE_URL": (base_url or "").strip(),
    }
    if include_api_key:
        values["MIANOTES_LLM_API_KEY"] = (api_key or "").strip()

    for key, value in values.items():
        upsert_env_value(env_file_path, key, value)
        os.environ[key] = value
    get_settings.cache_clear()
