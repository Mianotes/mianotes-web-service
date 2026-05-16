from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI

from mianotes_web_service.core.config import get_settings


class MiaUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: str | None = None


@dataclass(frozen=True)
class MiaTextResult:
    text: str
    provider: str
    model: str


LOCAL_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
LOCAL_LLM_MODEL = "llama3.2"


def _first_value(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _llm_config() -> LLMConfig:
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()

    if provider == "openai":
        api_key = _first_value(
            settings.llm_api_key,
            settings.openai_api_key,
            os.environ.get("OPENAI_API_KEY"),
        )
        if not api_key:
            raise MiaUnavailable("OpenAI API key is not configured")
        model = _first_value(
            settings.llm_model,
            os.environ.get("OPENAI_MODEL"),
            settings.openai_model,
        )
        return LLMConfig(
            provider="openai",
            model=model or "gpt-4o-mini",
            api_key=api_key,
            base_url=settings.llm_base_url,
        )

    if provider in {"local", "ollama"}:
        return LLMConfig(
            provider="local",
            model=_first_value(settings.llm_model, os.environ.get("OLLAMA_MODEL"), LOCAL_LLM_MODEL)
            or LOCAL_LLM_MODEL,
            api_key=_first_value(settings.llm_api_key, os.environ.get("OLLAMA_API_KEY"), "ollama")
            or "ollama",
            base_url=_first_value(
                settings.llm_base_url,
                os.environ.get("OLLAMA_BASE_URL"),
                LOCAL_LLM_BASE_URL,
            ),
        )

    if provider in {"openai-compatible", "compatible"}:
        if not settings.llm_base_url:
            raise MiaUnavailable("OpenAI-compatible LLM base URL is not configured")
        if not settings.llm_model:
            raise MiaUnavailable("OpenAI-compatible LLM model is not configured")
        return LLMConfig(
            provider="openai-compatible",
            model=settings.llm_model,
            api_key=_first_value(
                settings.llm_api_key,
                os.environ.get("OPENAI_API_KEY"),
                "local",
            )
            or "local",
            base_url=settings.llm_base_url,
        )

    raise MiaUnavailable(f"Unsupported LLM provider: {settings.llm_provider}")


def _client_for(config: LLMConfig) -> OpenAI:
    kwargs: dict[str, str] = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return OpenAI(**kwargs)


def summarise_markdown(*, title: str, markdown: str) -> MiaTextResult:
    config = _llm_config()
    client = _client_for(config)
    response = client.chat.completions.create(
        model=config.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Mia, the Mianotes assistant. Summarise notes into clear, "
                    "useful Markdown for humans and AI agents. Return Markdown body only."
                ),
            },
            {
                "role": "user",
                "content": f"Title: {title}\n\nMarkdown note:\n\n{markdown}",
            },
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise MiaUnavailable(f"{config.provider} returned an empty summary")
    return MiaTextResult(
        text=content.strip(),
        provider=config.provider,
        model=config.model,
    )
