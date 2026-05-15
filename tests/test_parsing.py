from pathlib import Path
from types import SimpleNamespace

import pytest

from mianotes_web_service.services import parsing
from mianotes_web_service.services.parsing import (
    DEFAULT_BROWSER_USER_AGENT,
    MarkItDownParser,
    ParserUnavailable,
    fetch_url_to_html,
    parse_document,
    parse_url,
)


def _fake_markitdown_module(text: str = "# Converted\n\nHello from MarkItDown."):
    class FakeMarkItDown:
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
