from pathlib import Path
from types import SimpleNamespace

import pytest

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.services import parsing
from mianotes_web_service.services.parsing import (
    DEFAULT_BROWSER_USER_AGENT,
    MarkItDownParser,
    ParserError,
    ParserUnavailable,
    fetch_url_to_html,
    parse_document,
    parse_html_document,
    parse_url,
)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fake_markitdown_module(text: str = "# Converted\n\nHello from MarkItDown."):
    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(text_content=f"{text}\n\nsource={Path(path).name}")

    return SimpleNamespace(MarkItDown=FakeMarkItDown)


def test_markitdown_parser_converts_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "note.md"
    source.write_text("# Hello\n\nMianotes parser layer.", encoding="utf-8")
    monkeypatch.setattr(
        parsing.importlib,
        "import_module",
        lambda _: _fake_markitdown_module(),
    )

    parsed = parse_document(source)

    assert parsed.parser == "markitdown"
    assert parsed.source_path == source
    assert "Hello from MarkItDown" in parsed.text
    assert "source=note.md" in parsed.text


def test_image_parser_uses_configured_llm_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "photo.jpeg"
    source.write_bytes(b"fake image")
    created_with = {}

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            created_with.update(kwargs)

        def convert(self, path: str):
            return SimpleNamespace(
                text_content=(
                    "ImageSize: 1179x1967\n\n"
                    "# Description:\n"
                    "A screenshot showing a Mianotes upload result."
                )
            )

    monkeypatch.setattr(
        parsing,
        "markitdown_llm_options",
        lambda: {
            "llm_client": object(),
            "llm_model": "llama3.2-vision",
            "llm_prompt": "Convert this image into useful Markdown.",
        },
    )
    monkeypatch.setattr(
        parsing.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == "A screenshot showing a Mianotes upload result."
    assert created_with["llm_model"] == "llama3.2-vision"
    assert "llm_client" in created_with
    assert "Convert this image into useful Markdown" in created_with["llm_prompt"]


def test_image_parser_rejects_metadata_only_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "photo.png"
    source.write_bytes(b"fake image")

    monkeypatch.setattr(
        parsing,
        "markitdown_llm_options",
        lambda: {
            "llm_client": object(),
            "llm_model": "llama3.2-vision",
            "llm_prompt": "Convert this image into useful Markdown.",
        },
    )
    monkeypatch.setattr(
        parsing.importlib,
        "import_module",
        lambda _: _fake_markitdown_module("ImageSize: 1179x1967"),
    )

    with pytest.raises(ParserError, match="metadata only"):
        parse_document(source)


def test_missing_markitdown_reports_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "file.pdf"
    source.write_bytes(b"%PDF")

    def missing_module(_: str):
        raise ModuleNotFoundError("No module named 'markitdown'")

    monkeypatch.setattr(parsing.importlib, "import_module", missing_module)

    with pytest.raises(ParserUnavailable, match="markitdown is not installed"):
        MarkItDownParser().parse(source)


def test_fetch_url_uses_browser_user_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"<html><body>ok</body></html>"

    def fake_urlopen(request, timeout: int):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(parsing, "urlopen", fake_urlopen)
    output_path = tmp_path / "page.html"

    fetched_path = fetch_url_to_html("https://example.com", output_path)

    assert fetched_path == output_path
    assert output_path.read_text(encoding="utf-8") == "<html><body>ok</body></html>"
    assert requests[0][0].get_header("User-agent") == DEFAULT_BROWSER_USER_AGENT
    assert requests[0][1] == 30


def test_parse_url_fetches_html_then_converts_local_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_fetch_url_to_html(url: str, output_path: Path, **_kwargs):
        output_path.write_text(f"<html>{url}</html>", encoding="utf-8")
        return output_path

    monkeypatch.setattr(parsing, "fetch_url_to_html", fake_fetch_url_to_html)
    monkeypatch.setattr(
        parsing.importlib,
        "import_module",
        lambda _: _fake_markitdown_module("Converted URL"),
    )

    parsed = parse_url("https://example.com/wiki", work_dir=tmp_path)

    assert parsed.parser == "markitdown"
    assert parsed.source_path == tmp_path / "page.html"
    assert "Converted URL" in parsed.text
    assert "source=page.html" in parsed.text


def test_parse_html_document_uses_trafilatura_cleaned_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "page.html"
    source.write_text(
        """
        <html>
          <body>
            <nav>This navigation should not be converted.</nav>
            <article>Clean article content for Mianotes. This paragraph has enough text
            for the extractor confidence threshold and should be kept for MarkItDown.</article>
            <footer>This footer should not be converted.</footer>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    class FakeMarkItDown:
        def convert(self, path: str):
            return SimpleNamespace(text_content=Path(path).read_text(encoding="utf-8"))

    fake_trafilatura = SimpleNamespace(
        extract=lambda *_args, **_kwargs: (
            "<article>Clean article content for Mianotes. This paragraph has enough text "
            "for the extractor confidence threshold and should be kept for MarkItDown.</article>"
        )
    )

    def fake_import_module(name: str):
        if name == "trafilatura":
            return fake_trafilatura
        if name == "markitdown":
            return SimpleNamespace(MarkItDown=FakeMarkItDown)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(parsing.importlib, "import_module", fake_import_module)

    parsed = parse_html_document(source, url="https://example.com/article")

    assert parsed.parser == "markitdown+trafilatura"
    assert parsed.source_path == source
    assert "Clean article content" in parsed.text
    assert "navigation should not" not in parsed.text
    assert "footer should not" not in parsed.text
