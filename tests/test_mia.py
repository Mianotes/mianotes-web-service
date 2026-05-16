from types import SimpleNamespace

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.services import mia


def _fake_openai(calls: dict[str, object]):
    class FakeCompletions:
        def create(self, **kwargs):
            calls["completion"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="## Summary\n\nUseful and tidy.")
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    return FakeOpenAI


def test_mia_uses_openai_provider(monkeypatch):
    calls: dict[str, object] = {}
    monkeypatch.setenv("MIANOTES_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MIANOTES_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(mia, "OpenAI", _fake_openai(calls))
    get_settings.cache_clear()

    result = mia.summarise_markdown(title="Test", markdown="# Test")

    assert result.text == "## Summary\n\nUseful and tidy."
    assert result.provider == "openai"
    assert result.model == "gpt-4o-mini"
    assert calls["client"] == {"api_key": "sk-test"}
    assert calls["completion"]["model"] == "gpt-4o-mini"
    get_settings.cache_clear()


def test_mia_uses_local_openai_compatible_provider(monkeypatch):
    calls: dict[str, object] = {}
    monkeypatch.setenv("MIANOTES_LLM_PROVIDER", "local")
    monkeypatch.setenv("MIANOTES_LLM_MODEL", "llama3.2")
    monkeypatch.setattr(mia, "OpenAI", _fake_openai(calls))
    get_settings.cache_clear()

    result = mia.summarise_markdown(title="Test", markdown="# Test")

    assert result.provider == "local"
    assert result.model == "llama3.2"
    assert calls["client"] == {
        "api_key": "ollama",
        "base_url": "http://127.0.0.1:11434/v1",
    }
    assert calls["completion"]["model"] == "llama3.2"
    get_settings.cache_clear()
