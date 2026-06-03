import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.services import (
    parser_audio,
    parser_image,
    parser_markitdown,
    parser_pdf,
    parser_tools,
    parser_url,
    parsing,
)
from mianotes_web_service.services.parsing import (
    DEFAULT_BROWSER_USER_AGENT,
    DOCUMENT_UNREADABLE_MESSAGE,
    IMAGE_NEEDS_CLOUD_MESSAGE,
    IMAGE_UNREADABLE_MESSAGE,
    MarkItDownParser,
    ParserError,
    ParserUnavailable,
    fetch_url_to_html,
    is_youtube_url,
    parse_document,
    parse_html_document,
    parse_url,
    parse_youtube_url,
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
        parser_markitdown.importlib,
        "import_module",
        lambda _: _fake_markitdown_module(),
    )

    parsed = parse_document(source)

    assert parsed.parser == "markitdown"
    assert parsed.source_path == source
    assert "Hello from MarkItDown" in parsed.text
    assert "source=note.md" in parsed.text


def test_document_parser_retries_blank_document_with_ocr_plugin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "scanned.pdf"
    source.write_bytes(b"%PDF")
    created_with = []

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            created_with.append(kwargs)

        def convert(self, path: str):
            if created_with[-1].get("enable_plugins"):
                return SimpleNamespace(text_content="Scanned PDF text")
            return SimpleNamespace(text_content="")

    monkeypatch.setattr(
        parsing,
        "markitdown_llm_options",
        lambda: {
            "llm_client": object(),
            "llm_model": "gpt-4o",
        },
    )
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == "Scanned PDF text"
    assert parsed.parser == "markitdown+ocr"
    assert created_with == [
        {},
        {
            "enable_plugins": True,
            "llm_client": created_with[1]["llm_client"],
            "llm_model": "gpt-4o",
        },
    ]


def test_document_parser_unwraps_markitdown_ocr_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "scanned.pdf"
    source.write_bytes(b"%PDF")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(
                text_content=(
                    "## Page 1\n\n"
                    "*[Image OCR]\n"
                    "```markdown\n"
                    "# THE PRODUCT-LED GROWTH MANIFESTO\n\n"
                    "**Building a SaaS product that sells itself.**\n"
                    "```\n"
                    "[End OCR]*\n\n"
                    "## Page 2\n\n"
                    "*[Image OCR]\n"
                    "```markdown\n"
                    "# Three forces threatening traditional SaaS.\n"
                    "```\n"
                    "[End OCR]*\n"
                )
            )

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == (
        "## Page 1\n\n"
        "# THE PRODUCT-LED GROWTH MANIFESTO\n\n"
        "**Building a SaaS product that sells itself.**\n\n"
        "## Page 2\n\n"
        "# Three forces threatening traditional SaaS."
    )
    assert "[Image OCR]" not in parsed.text
    assert "```" not in parsed.text


def test_document_parser_removes_unfenced_ocr_markers_and_self_closes_breaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "scanned.pdf"
    source.write_bytes(b"%PDF")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(
                text_content=(
                    "## Page 1\n\n"
                    "*[Image OCR]\n"
                    "| Product Manager | Project Manager |\n"
                    "| --- | --- |\n"
                    "| Strategy<br>Vision | Delivery<br>Timeline |\n"
                    "[End OCR]*\n"
                )
            )

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == (
        "## Page 1\n\n"
        "| Product Manager | Project Manager |\n"
        "| --- | --- |\n"
        "| Strategy<br />Vision | Delivery<br />Timeline |"
    )


def test_document_parser_uses_local_tesseract_for_blank_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "scanned.pdf"
    source.write_bytes(b"%PDF")
    rendered_pages: list[Path] = []
    tesseract = tmp_path / "tesseract"
    tesseract.write_text("fake executable", encoding="utf-8")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, _path: str):
            return SimpleNamespace(text_content="")

    def fake_render_pdf_pages(_source_path: Path, output_dir: Path) -> list[Path]:
        first_page = output_dir / "page-0001.png"
        second_page = output_dir / "page-0002.png"
        first_page.write_bytes(b"page one")
        second_page.write_bytes(b"page two")
        rendered_pages.extend([first_page, second_page])
        return [first_page, second_page]

    def fake_run(args, **_kwargs):
        if args[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="tesseract 5.5.0", stderr="")
        page_name = Path(args[1]).name
        return SimpleNamespace(returncode=0, stdout=f"Text from {page_name}", stderr="")

    monkeypatch.setattr(
        parsing,
        "markitdown_llm_options",
        lambda: (_ for _ in ()).throw(parsing.MiaUnavailable("LLM is not configured")),
    )
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(shutil, "which", lambda command: str(tesseract))
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(parser_pdf, "render_pdf_pages_for_ocr", fake_render_pdf_pages)
    monkeypatch.setattr(parser_image, "preprocess_image_for_ocr", lambda *_args: None)

    parsed = parse_document(source)

    assert parsed.parser == "markitdown+ocr"
    assert parsed.text == (
        "## Document OCR\n\n"
        "## Page 1\n\n"
        "Text from page-0001.png\n\n"
        "## Page 2\n\n"
        "Text from page-0002.png"
    )
    assert len(rendered_pages) == 2


def test_document_parser_reports_unreadable_when_pdf_ocr_has_no_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "scanned.pdf"
    source.write_bytes(b"%PDF")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, _path: str):
            return SimpleNamespace(text_content="")

    monkeypatch.setattr(
        parsing,
        "markitdown_llm_options",
        lambda: (_ for _ in ()).throw(parsing.MiaUnavailable("LLM is not configured")),
    )
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(parser_pdf, "tesseract_pdf_ocr", lambda _path: None)

    parsed = parse_document(source)

    assert parsed.parser == "markitdown+ocr"
    assert parsed.text == DOCUMENT_UNREADABLE_MESSAGE


def test_document_parser_self_closes_html_void_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "html.md"
    source.write_text("# HTML", encoding="utf-8")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(
                text_content=(
                    "![Logo](logo.png)\n\n"
                    '<img src="logo.png" alt="Logo">\n'
                    "<hr>\n"
                    '<input type="checkbox" checked>\n'
                )
            )

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == (
        "![Logo](logo.png)\n\n"
        '<img src="logo.png" alt="Logo" />\n'
        "<hr />\n"
        '<input type="checkbox" checked />\n'
    )


def test_document_parser_preserves_regular_markdown_code_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "code.md"
    source.write_text("# Code example", encoding="utf-8")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(
                text_content=(
                    "# Code example\n\n"
                    "```python\n"
                    "print('<br>')\n"
                    "print('<img src=\"logo.png\">')\n"
                    "```\n"
                )
            )

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == (
        "# Code example\n\n```python\nprint('<br>')\nprint('<img src=\"logo.png\">')\n```\n"
    )


def test_document_parser_escapes_mdx_unsafe_pdf_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(
                text_content=(
                    "Results were significant at p<0.001.\n\n"
                    "The runner injects <tick> prompts.\n\n"
                    "Session files live under history/<sessionId>/.\n\n"
                    "</>\n"
                )
            )

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == (
        "Results were significant at p&lt;0.001.\n\n"
        "The runner injects &lt;tick&gt; prompts.\n\n"
        "Session files live under history/&lt;sessionId&gt;/.\n\n"
        "&lt;/>\n"
    )


def test_document_parser_preserves_html_tags_autolinks_and_code_when_escaping_mdx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(
                text_content=(
                    "<span>Visible label</span>\n"
                    "<https://example.com/paper.pdf>\n"
                    "<team@example.com>\n\n"
                    "```text\n"
                    "p<0.001 and <tick> stay literal in code\n"
                    "```\n"
                )
            )

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == (
        "<span>Visible label</span>\n"
        "<https://example.com/paper.pdf>\n"
        "<team@example.com>\n\n"
        "```text\n"
        "p<0.001 and <tick> stay literal in code\n"
        "```\n"
    )


def test_document_parser_escapes_accidental_text_directives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(
                text_content=(
                    "1v82241.4062:viXra\n"
                    "Bash(prefix:npm)\n"
                    "model():what the model can reach\n\n"
                    ":::note\n"
                    "Keep real admonitions available.\n"
                    ":::\n\n"
                    "```text\n"
                    "prefix:npm stays literal in code\n"
                    "```\n"
                )
            )

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == (
        "1v82241.4062\\:viXra\n"
        "Bash(prefix\\:npm)\n"
        "model()\\:what the model can reach\n\n"
        ":::note\n"
        "Keep real admonitions available.\n"
        ":::\n\n"
        "```text\n"
        "prefix:npm stays literal in code\n"
        "```\n"
    )


def test_document_parser_adds_feedback_when_ocr_llm_is_not_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "scanned.pdf"
    source.write_bytes(b"%PDF")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(text_content="")

    monkeypatch.setattr(
        parsing,
        "markitdown_llm_options",
        lambda: (_ for _ in ()).throw(parsing.MiaUnavailable("OpenAI is not configured")),
    )
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == DOCUMENT_UNREADABLE_MESSAGE
    assert parsed.parser == "markitdown+ocr"


def test_document_parser_adds_feedback_when_ocr_returns_no_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "scanned.pdf"
    source.write_bytes(b"%PDF")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(text_content="")

    monkeypatch.setattr(
        parsing,
        "markitdown_llm_options",
        lambda: {
            "llm_client": object(),
            "llm_model": "gpt-4o",
        },
    )
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == DOCUMENT_UNREADABLE_MESSAGE
    assert parsed.parser == "markitdown+ocr"


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
        "markitdown_openai_image_options",
        lambda: {
            "llm_client": object(),
            "llm_model": "llama3.2-vision",
            "llm_prompt": "Convert this image into useful Markdown.",
        },
    )
    monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == "A screenshot showing a Mianotes upload result."
    assert created_with["llm_model"] == "llama3.2-vision"
    assert "llm_client" in created_with
    assert "Convert this image into useful Markdown" in created_with["llm_prompt"]


def test_image_parser_uses_tesseract_before_llm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "screenshot.png"
    source.write_bytes(b"fake image")
    tesseract = tmp_path / "tesseract"
    tesseract.write_text("fake executable", encoding="utf-8")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="Receipt total\n\n\n£42.50\n",
        )

    monkeypatch.setattr(shutil, "which", lambda command: str(tesseract))
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(parser_image, "preprocess_image_for_ocr", lambda *_args: None)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: _fake_markitdown_module("ImageSize: 1179x1967"),
    )

    parsed = parse_document(source)

    assert parsed.parser == "markitdown+tesseract"
    assert parsed.text == "Receipt total\n\n£42.50"


def test_image_parser_strips_ocr_code_block_indentation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "screenshot.png"
    source.write_bytes(b"fake image")
    tesseract = tmp_path / "tesseract"
    tesseract.write_text("fake executable", encoding="utf-8")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "    # Mianotes\n\n    ## Getting started\n\n    Useful text from a screenshot.\n"
            ),
        )

    monkeypatch.setattr(shutil, "which", lambda command: str(tesseract))
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(parser_image, "preprocess_image_for_ocr", lambda *_args: None)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: _fake_markitdown_module("ImageSize: 1179x1967"),
    )

    parsed = parse_document(source)

    assert parsed.text == "# Mianotes\n\n## Getting started\n\nUseful text from a screenshot."


def test_image_parser_strips_markdown_fence_from_llm_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "photo.jpeg"
    source.write_bytes(b"fake image")

    class FakeMarkItDown:
        def __init__(self, **_kwargs):
            pass

        def convert(self, path: str):
            return SimpleNamespace(
                text_content=(
                    "ImageSize: 1179x1967\n\n"
                    "# Description:\n"
                    "```markdown\n"
                    "# Mianotes\n\n"
                    "## Getting started\n"
                    "```\n"
                )
            )

    monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setattr(
        parsing,
        "markitdown_openai_image_options",
        lambda: {
            "llm_client": object(),
            "llm_model": "gpt-4o-mini",
            "llm_prompt": "Convert this image into useful Markdown.",
        },
    )
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == "# Mianotes\n\n## Getting started"


def test_tesseract_executable_skips_broken_path_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    broken = tmp_path / "broken-tesseract"
    working = tmp_path / "working-tesseract"
    broken.write_text("broken", encoding="utf-8")
    working.write_text("working", encoding="utf-8")

    def fake_run(args, **_kwargs):
        if args[0] == str(broken):
            raise OSError("Bad CPU type in executable")
        return SimpleNamespace(returncode=0, stdout="tesseract 5.5.0")

    monkeypatch.setattr(shutil, "which", lambda command: str(broken))
    monkeypatch.setattr(parser_image, "TESSERACT_CANDIDATES", (str(working),))
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("MIANOTES_SETTINGS_PATH", str(tmp_path / "missing-settings.json"))
    get_settings.cache_clear()

    assert parser_image.tesseract_executable() == str(working)


def test_image_parser_falls_back_to_llm_when_tesseract_has_no_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "photo.png"
    source.write_bytes(b"fake image")
    created_with = {}

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            created_with.update(kwargs)

        def convert(self, path: str):
            return SimpleNamespace(text_content="# Description:\nA photo of a whiteboard.")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="   ")

    monkeypatch.setattr(shutil, "which", lambda command: "/usr/bin/tesseract")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(parser_image, "preprocess_image_for_ocr", lambda *_args: None)
    monkeypatch.setattr(
        parsing,
        "markitdown_openai_image_options",
        lambda: {
            "llm_client": object(),
            "llm_model": "gpt-4o-mini",
            "llm_prompt": "Convert this image into useful Markdown.",
        },
    )
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == "A photo of a whiteboard."
    assert parsed.parser == "markitdown+tesseract+openai"
    assert created_with["llm_model"] == "gpt-4o-mini"


def test_image_parser_adds_feedback_when_cloud_llm_is_not_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "photo.png"
    source.write_bytes(b"fake image")

    monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setattr(
        parsing,
        "markitdown_openai_image_options",
        lambda: (_ for _ in ()).throw(parsing.MiaUnavailable("OpenAI is not configured")),
    )
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: _fake_markitdown_module("ImageSize: 1179x1967"),
    )

    parsed = parse_document(source)

    assert parsed.parser == "markitdown+tesseract"
    assert parsed.text == IMAGE_NEEDS_CLOUD_MESSAGE


def test_image_parser_adds_feedback_when_cloud_llm_finds_no_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "photo.png"
    source.write_bytes(b"fake image")

    monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setattr(
        parsing,
        "markitdown_openai_image_options",
        lambda: {
            "llm_client": object(),
            "llm_model": "gpt-4o-mini",
            "llm_prompt": "Convert this image into useful Markdown.",
        },
    )
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: _fake_markitdown_module("ImageSize: 1179x1967"),
    )

    parsed = parse_document(source)

    assert parsed.parser == "markitdown+tesseract+openai"
    assert parsed.text == IMAGE_UNREADABLE_MESSAGE


def test_missing_markitdown_reports_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "file.pdf"
    source.write_bytes(b"%PDF")

    def missing_module(_: str):
        raise ModuleNotFoundError("No module named 'markitdown'")

    monkeypatch.setattr(parser_markitdown.importlib, "import_module", missing_module)

    with pytest.raises(ParserUnavailable, match="markitdown is not installed"):
        MarkItDownParser().parse(source)


def test_audio_parser_retries_with_low_quality_mp3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "recording.m4a"
    source.write_bytes(b"fake audio")
    commands = []

    class FakeMarkItDown:
        def convert(self, path: str):
            if path.endswith("recording.m4a"):
                raise RuntimeError("recognition connection failed")
            return SimpleNamespace(text_content="Transcribed fallback audio")

    def fake_run(args, **_kwargs):
        if args[-1] in {"-version", "--version"}:
            return SimpleNamespace(returncode=0, stdout="ffmpeg ok", stderr="")
        commands.append(args)
        Path(args[-1]).write_bytes(b"low quality mp3")
        return SimpleNamespace(returncode=0, stdout="", stderr="encoded")

    monkeypatch.setattr(shutil, "which", lambda command: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.parser == "markitdown+ffmpeg-mp3"
    assert parsed.text == "Transcribed fallback audio"
    assert parsed.source_path == source
    assert commands[0][:8] == [
        "/opt/homebrew/bin/ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
    ]
    assert commands[0][-1].endswith("low-quality.mp3")


def test_audio_parser_treats_mp4_as_audio():
    assert parser_audio.is_audio(Path("recording.mp4"))


def test_audio_parser_splits_audio_when_low_quality_mp3_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "recording.m4a"
    source.write_bytes(b"fake long audio")
    commands = []

    class FakeMarkItDown:
        def convert(self, path: str):
            name = Path(path).name
            if name in {"recording.m4a", "low-quality.mp3"}:
                raise RuntimeError(f"could not transcribe {name}")
            if name == "chunk-000.mp3":
                return SimpleNamespace(text_content="First chunk transcript")
            if name == "chunk-001.mp3":
                return SimpleNamespace(text_content="Second chunk transcript")
            return SimpleNamespace(text_content="")

    def fake_run(args, **_kwargs):
        if args[-1] in {"-version", "--version"}:
            return SimpleNamespace(returncode=0, stdout="ffmpeg ok", stderr="")
        commands.append(args)
        if "segment" in args:
            chunk_dir = Path(args[-1]).parent
            chunk_dir.mkdir(parents=True, exist_ok=True)
            (chunk_dir / "chunk-000.mp3").write_bytes(b"chunk one")
            (chunk_dir / "chunk-001.mp3").write_bytes(b"chunk two")
        else:
            Path(args[-1]).write_bytes(b"low quality mp3")
        return SimpleNamespace(returncode=0, stdout="", stderr="encoded")

    monkeypatch.setattr(shutil, "which", lambda command: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.parser == "markitdown+ffmpeg-mp3"
    assert parsed.text == (
        "## Audio transcript\n\n"
        "### Part 1\n\n"
        "First chunk transcript\n\n"
        "### Part 2\n\n"
        "Second chunk transcript"
    )
    assert len(commands) == 2
    assert commands[1][-7:] == [
        "-f",
        "segment",
        "-segment_time",
        str(parsing.AUDIO_CHUNK_SECONDS),
        "-reset_timestamps",
        "1",
        commands[1][-1],
    ]


def test_audio_parser_skips_chunks_without_detected_speech(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "recording.m4a"
    source.write_bytes(b"fake long audio")

    class FakeMarkItDown:
        def convert(self, path: str):
            name = Path(path).name
            if name in {"recording.m4a", "low-quality.mp3", "chunk-000.mp3"}:
                raise RuntimeError(
                    "File conversion failed after 1 attempts:\n"
                    " - AudioConverter threw UnknownValueError with message: "
                )
            if name == "chunk-001.mp3":
                return SimpleNamespace(text_content="Second chunk transcript")
            return SimpleNamespace(text_content="")

    def fake_run(args, **_kwargs):
        if args[-1] in {"-version", "--version"}:
            return SimpleNamespace(returncode=0, stdout="ffmpeg ok", stderr="")
        if "segment" in args:
            chunk_dir = Path(args[-1]).parent
            chunk_dir.mkdir(parents=True, exist_ok=True)
            (chunk_dir / "chunk-000.mp3").write_bytes(b"chunk one")
            (chunk_dir / "chunk-001.mp3").write_bytes(b"chunk two")
        else:
            Path(args[-1]).write_bytes(b"low quality mp3")
        return SimpleNamespace(returncode=0, stdout="", stderr="encoded")

    monkeypatch.setattr(shutil, "which", lambda command: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == "## Audio transcript\n\n### Part 2\n\nSecond chunk transcript"


def test_audio_parser_reports_no_detected_speech_when_all_chunks_are_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "recording.m4a"
    source.write_bytes(b"fake silent audio")

    class FakeMarkItDown:
        def convert(self, _path: str):
            raise RuntimeError(
                "File conversion failed after 1 attempts:\n"
                " - AudioConverter threw UnknownValueError with message: "
            )

    def fake_run(args, **_kwargs):
        if args[-1] in {"-version", "--version"}:
            return SimpleNamespace(returncode=0, stdout="ffmpeg ok", stderr="")
        if "segment" in args:
            chunk_dir = Path(args[-1]).parent
            chunk_dir.mkdir(parents=True, exist_ok=True)
            (chunk_dir / "chunk-000.mp3").write_bytes(b"chunk one")
        else:
            Path(args[-1]).write_bytes(b"low quality mp3")
        return SimpleNamespace(returncode=0, stdout="", stderr="encoded")

    monkeypatch.setattr(shutil, "which", lambda command: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    with pytest.raises(ParserError, match=parsing.NO_AUDIO_SPEECH_MESSAGE):
        parse_document(source)


def test_audio_parser_reports_original_and_fallback_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "recording.m4a"
    source.write_bytes(b"fake audio")

    class FakeMarkItDown:
        def convert(self, path: str):
            raise RuntimeError(f"could not transcribe {Path(path).name}")

    def fake_run(args, **_kwargs):
        if args[-1] in {"-version", "--version"}:
            return SimpleNamespace(returncode=0, stdout="ffmpeg ok", stderr="")
        if "segment" in args:
            chunk_dir = Path(args[-1]).parent
            chunk_dir.mkdir(parents=True, exist_ok=True)
            (chunk_dir / "chunk-000.mp3").write_bytes(b"chunk one")
        else:
            Path(args[-1]).write_bytes(b"low quality mp3")
        return SimpleNamespace(returncode=0, stdout="", stderr="encoded")

    monkeypatch.setattr(shutil, "which", lambda command: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    with pytest.raises(ParserError, match="chunk-000.mp3"):
        parse_document(source)


def test_ffmpeg_executable_skips_broken_path(monkeypatch: pytest.MonkeyPatch):
    commands: list[list[str]] = []

    def fake_run(args, **_kwargs):
        commands.append(args)
        if args[0] == "/broken/ffmpeg":
            return SimpleNamespace(returncode=126, stdout="", stderr="Bad CPU type in executable")
        return SimpleNamespace(returncode=0, stdout="ffmpeg version 8.1", stderr="")

    monkeypatch.setattr(parser_tools, "FFMPEG_CANDIDATES", ("ffmpeg", "/working/ffmpeg"))
    monkeypatch.setattr(shutil, "which", lambda command: "/broken/ffmpeg")
    monkeypatch.setattr(Path, "exists", lambda path: str(path) == "/working/ffmpeg")
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert parser_tools.ffmpeg_executable() == "/working/ffmpeg"
    assert commands == [["/broken/ffmpeg", "-version"], ["/working/ffmpeg", "-version"]]


def test_audio_parser_prefers_verified_audio_tool_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    good_dir = tmp_path / "opt" / "bin"
    bad_dir = tmp_path / "usr" / "local" / "bin"
    good_dir.mkdir(parents=True)
    bad_dir.mkdir(parents=True)
    for directory in (good_dir, bad_dir):
        for tool in ("ffmpeg", "flac"):
            (directory / tool).write_text("", encoding="utf-8")

    def fake_run(args, **_kwargs):
        if str(args[0]).startswith(str(bad_dir)):
            return SimpleNamespace(returncode=126, stdout="", stderr="Bad CPU type in executable")
        return SimpleNamespace(returncode=0, stdout=f"{Path(args[0]).name} ok", stderr="")

    monkeypatch.setattr(parser_tools, "AUDIO_TOOL_NAMES", ("ffmpeg", "flac"))
    monkeypatch.setattr(
        parser_tools,
        "AUDIO_TOOL_VERSION_ARGS",
        {"ffmpeg": "-version", "flac": "--version"},
    )
    monkeypatch.setattr(parser_tools, "AUDIO_TOOL_DIR_CANDIDATES", (str(good_dir), str(bad_dir)))
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("PATH", f"{bad_dir}:/usr/bin")

    with parser_tools.prefer_working_audio_tools():
        assert os.environ["PATH"].split(":")[0] == str(good_dir)

    assert os.environ["PATH"] == f"{bad_dir}:/usr/bin"


def test_fetch_url_uses_browser_user_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    requests = []

    class FakeResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://example.com"

        def read(self, _size: int = -1):
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return b"<html><body>ok</body></html>"

    def fake_open_url(request, *, timeout: int):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(
        parser_url,
        "_resolve_host_addresses",
        lambda _hostname: [parser_url.ipaddress.ip_address("93.184.216.34")],
    )
    monkeypatch.setattr(parser_url, "_open_url", fake_open_url)
    output_path = tmp_path / "page.html"

    fetched_path = fetch_url_to_html("https://example.com", output_path)

    assert fetched_path == output_path
    assert output_path.read_text(encoding="utf-8") == "<html><body>ok</body></html>"
    assert requests[0][0].get_header("User-agent") == DEFAULT_BROWSER_USER_AGENT
    assert requests[0][1] == 30


def test_fetch_url_rejects_private_hosts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def fake_open_url(*_args, **_kwargs):
        raise AssertionError("private hosts should be rejected before fetching")

    monkeypatch.setattr(parser_url, "_open_url", fake_open_url)

    with pytest.raises(ParserError, match="URL host is not allowed"):
        fetch_url_to_html("http://127.0.0.1/admin", tmp_path / "page.html")


def test_fetch_url_enforces_max_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://example.com"

        def read(self, _size: int = -1):
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return b"too large"

    monkeypatch.setattr(
        parser_url,
        "_resolve_host_addresses",
        lambda _hostname: [parser_url.ipaddress.ip_address("93.184.216.34")],
    )
    monkeypatch.setattr(parser_url, "_open_url", lambda *_args, **_kwargs: FakeResponse())
    output_path = tmp_path / "page.html"

    with pytest.raises(ParserError, match="URL response is too large"):
        fetch_url_to_html("https://example.com", output_path, max_bytes=3)

    assert not output_path.exists()


def test_fetch_url_rejects_private_redirects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def fake_resolve(hostname: str):
        if hostname == "example.com":
            return [parser_url.ipaddress.ip_address("93.184.216.34")]
        if hostname == "127.0.0.1":
            return [parser_url.ipaddress.ip_address("127.0.0.1")]
        raise AssertionError(hostname)

    def fake_open_url(_request, *, timeout: int):
        raise parser_url.HTTPError(
            "https://example.com",
            302,
            "Found",
            {"Location": "http://127.0.0.1/admin"},
            None,
        )

    monkeypatch.setattr(parser_url, "_resolve_host_addresses", fake_resolve)
    monkeypatch.setattr(parser_url, "_open_url", fake_open_url)

    with pytest.raises(ParserError, match="URL host is not allowed"):
        fetch_url_to_html("https://example.com", tmp_path / "page.html")


def test_parse_url_fetches_html_then_converts_local_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_fetch_url_to_html(url: str, output_path: Path, **_kwargs):
        output_path.write_text(f"<html>{url}</html>", encoding="utf-8")
        return output_path

    monkeypatch.setattr(parsing, "fetch_url_to_html", fake_fetch_url_to_html)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: _fake_markitdown_module("Converted URL"),
    )

    parsed = parse_url("https://example.com/wiki", work_dir=tmp_path)

    assert parsed.parser == "markitdown"
    assert parsed.source_path == tmp_path / "page.html"
    assert "Converted URL" in parsed.text
    assert "source=page.html" in parsed.text


def test_parse_url_downloads_remote_file_then_converts_source_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    fetched: list[tuple[str, Path]] = []

    def fake_fetch_url_to_file(url: str, output_path: Path, **_kwargs):
        fetched.append((url, output_path))
        output_path.write_bytes(b"%PDF-1.4")
        return output_path

    monkeypatch.setattr(parsing, "fetch_url_to_file", fake_fetch_url_to_file)
    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: _fake_markitdown_module("Converted PDF"),
    )

    url = "https://cdn.openai.com/business-guides-and-resources/identifying-and-scaling-ai-use-cases.pdf"
    parsed = parse_url(url, work_dir=tmp_path)

    assert fetched == [(url, tmp_path / "source.pdf")]
    assert parsed.parser == "markitdown"
    assert parsed.source_path == tmp_path / "source.pdf"
    assert "Converted PDF" in parsed.text
    assert "source=source.pdf" in parsed.text


def test_is_youtube_url_accepts_common_video_urls():
    assert is_youtube_url("https://www.youtube.com/watch?v=abc123")
    assert is_youtube_url("https://youtu.be/abc123")
    assert is_youtube_url("https://youtube.com/shorts/abc123")
    assert is_youtube_url("https://music.youtube.com/watch?v=abc123")


def test_is_youtube_url_rejects_non_video_or_non_youtube_urls():
    assert not is_youtube_url("https://www.youtube.com/feed/subscriptions")
    assert not is_youtube_url("https://example.com/watch?v=abc123")
    assert not is_youtube_url("file:///tmp/watch?v=abc123")


def test_parse_youtube_url_uses_markitdown_directly(monkeypatch: pytest.MonkeyPatch):
    seen: list[str] = []

    class FakeMarkItDown:
        def convert(self, value: str):
            seen.append(value)
            return SimpleNamespace(text_content="# Video\n\n### Transcript\n\nTranscript text.")

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    url = "https://www.youtube.com/watch?v=abc123"
    parsed = parse_youtube_url(url)

    assert parsed.parser == "markitdown+youtube"
    assert parsed.source_path == Path(url)
    assert seen == [url]
    assert "Transcript text" in parsed.text


def test_parse_youtube_url_rejects_footer_fallback(monkeypatch: pytest.MonkeyPatch):
    class FakeMarkItDown:
        def convert(self, _value: str):
            return SimpleNamespace(
                text_content=(
                    "[About](https://www.youtube.com/about/)"
                    "[Press](https://www.youtube.com/about/press/)\n\n"
                    "© 2026 Google LLC"
                )
            )

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    with pytest.raises(ParserError, match="Could not extract a YouTube transcript"):
        parse_youtube_url("https://www.youtube.com/watch?v=abc123")


def test_parse_youtube_url_falls_back_to_ytdlp_captions(monkeypatch: pytest.MonkeyPatch):
    commands: list[list[str]] = []

    class FakeMarkItDown:
        def convert(self, _value: str):
            return SimpleNamespace(text_content="[About](https://www.youtube.com/about/)")

    def fake_run(command_parts, **_kwargs):
        commands.append(command_parts)
        output_template = Path(command_parts[command_parts.index("-o") + 1])
        caption_path = output_template.parent / "abc123.en.vtt"
        caption_path.write_text(
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:02.000\n"
            "<c>Hello from captions</c>\n\n"
            "00:00:02.000 --> 00:00:04.000\n"
            "Second line\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command_parts, 0, stdout="ok", stderr="")

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    parsed = parse_youtube_url("https://www.youtube.com/watch?v=abc123")

    assert parsed.parser == "yt-dlp+captions"
    assert "Hello from captions" in parsed.text
    assert "Second line" in parsed.text
    assert commands[0][0].endswith("yt-dlp")
    assert "--skip-download" in commands[0]


def test_parse_youtube_url_falls_back_to_ytdlp_audio(monkeypatch: pytest.MonkeyPatch):
    commands: list[list[str]] = []

    class FakeMarkItDown:
        def convert(self, _value: str):
            return SimpleNamespace(text_content="[About](https://www.youtube.com/about/)")

    def fake_run(command_parts, **_kwargs):
        commands.append(command_parts)
        if "--skip-download" in command_parts:
            return subprocess.CompletedProcess(command_parts, 1, stdout="", stderr="no captions")
        output_template = Path(command_parts[command_parts.index("-o") + 1])
        audio_path = output_template.parent / "abc123.webm"
        audio_path.write_text("audio", encoding="utf-8")
        return subprocess.CompletedProcess(command_parts, 0, stdout="ok", stderr="")

    def fake_parse_document(path: Path):
        return parsing.ParsedDocument(
            text="Transcript from downloaded audio",
            parser="markitdown+ffmpeg-mp3",
            source_path=path,
        )

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(parsing, "parse_document", fake_parse_document)

    parsed = parse_youtube_url("https://www.youtube.com/watch?v=abc123")

    assert parsed.parser == "markitdown+ffmpeg-mp3+yt-dlp-audio"
    assert parsed.text == "Transcript from downloaded audio"
    assert "--skip-download" in commands[0]
    assert "-f" in commands[1]


def test_parse_youtube_url_reports_no_captions_or_speech(monkeypatch: pytest.MonkeyPatch):
    class FakeMarkItDown:
        def convert(self, _value: str):
            return SimpleNamespace(text_content="[About](https://www.youtube.com/about/)")

    def fake_run(command_parts, **_kwargs):
        if "--skip-download" in command_parts:
            return subprocess.CompletedProcess(
                command_parts,
                0,
                stdout="There are no subtitles for the requested languages",
                stderr="",
            )
        output_template = Path(command_parts[command_parts.index("-o") + 1])
        audio_path = output_template.parent / "abc123.webm"
        audio_path.write_text("audio", encoding="utf-8")
        return subprocess.CompletedProcess(command_parts, 0, stdout="ok", stderr="")

    def fake_parse_document(_path: Path):
        raise ParserError(parsing.NO_AUDIO_SPEECH_MESSAGE)

    monkeypatch.setattr(
        parser_markitdown.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(parsing, "parse_document", fake_parse_document)

    with pytest.raises(
        ParserError,
        match="This video has no captions, and Mia could not detect speech in the audio.",
    ):
        parse_youtube_url("https://www.youtube.com/watch?v=abc123")


def test_youtube_downloader_executable_finds_venv_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    python_path = tmp_path / "bin" / "python"
    downloader_path = tmp_path / "bin" / "yt-dlp"
    downloader_path.parent.mkdir()
    python_path.write_text("", encoding="utf-8")
    downloader_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(sys, "executable", str(python_path))

    assert parser_tools.youtube_downloader_executable() == str(downloader_path)


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

    monkeypatch.setattr(parser_markitdown.importlib, "import_module", fake_import_module)

    parsed = parse_html_document(source, url="https://example.com/article")

    assert parsed.parser == "markitdown+trafilatura"
    assert parsed.source_path == source
    assert "Clean article content" in parsed.text
    assert "navigation should not" not in parsed.text
    assert "footer should not" not in parsed.text
