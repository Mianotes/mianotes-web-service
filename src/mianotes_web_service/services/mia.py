from __future__ import annotations

import os

from openai import OpenAI

from mianotes_web_service.core.config import get_settings


class MiaUnavailable(RuntimeError):
    pass


def _openai_api_key() -> str:
    settings = get_settings()
    api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise MiaUnavailable("OpenAI API key is not configured")
    return api_key


def _openai_model() -> str:
    settings = get_settings()
    if settings.openai_model != "gpt-4o-mini":
        return settings.openai_model
    return os.environ.get("OPENAI_MODEL") or settings.openai_model


def summarise_markdown(*, title: str, markdown: str) -> str:
    client = OpenAI(api_key=_openai_api_key())
    response = client.chat.completions.create(
        model=_openai_model(),
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
        raise MiaUnavailable("OpenAI returned an empty summary")
    return content.strip()
