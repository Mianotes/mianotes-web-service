from pathlib import Path
from types import SimpleNamespace

import pytest

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.services import parsing
from mianotes_web_service.services.parsing import (
    DEFAULT_BROWSER_USER_AGENT,
    DOCUMENT_UNREADABLE_MESSAGE,
    IMAGE_NEEDS_CLOUD_MESSAGE,
    IMAGE_UNREADABLE_MESSAGE,
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
        parsing.importlib,
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
        parsing.importlib,
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
        parsing.importlib,
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
        parsing.importlib,
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
        parsing.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    parsed = parse_document(source)

    assert parsed.text == (
        "# Code example\n\n"
        "```python\n"
        "print('<br>')\n"
        "print('<img src=\"logo.png\">')\n"
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
        parsing.importlib,
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
        parsing.importlib,
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
    monkeypatch.setattr(parsing.shutil, "which", lambda command: None)
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

    monkeypatch.setattr(parsing.shutil, "which", lambda command: str(tesseract))
    monkeypatch.setattr(parsing.subprocess, "run", fake_run)
    monkeypatch.setattr(parsing, "_preprocess_image_for_ocr", lambda *_args: None)
    monkeypatch.setattr(
        parsing.importlib,
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
                "    # Mianotes\n\n"
                "    ## Getting started\n\n"
                "    Useful text from a screenshot.\n"
            ),
        )

    monkeypatch.setattr(parsing.shutil, "which", lambda command: str(tesseract))
    monkeypatch.setattr(parsing.subprocess, "run", fake_run)
    monkeypatch.setattr(parsing, "_preprocess_image_for_ocr", lambda *_args: None)
    monkeypatch.setattr(
        parsing.importlib,
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

    monkeypatch.setattr(parsing.shutil, "which", lambda command: None)
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
        parsing.importlib,
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

    monkeypatch.setattr(parsing.shutil, "which", lambda command: str(broken))
    monkeypatch.setattr(parsing, "TESSERACT_CANDIDATES", (str(working),))
    monkeypatch.setattr(parsing.subprocess, "run", fake_run)

    assert parsing._tesseract_executable() == str(working)


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

    monkeypatch.setattr(parsing.shutil, "which", lambda command: "/usr/bin/tesseract")
    monkeypatch.setattr(parsing.subprocess, "run", fake_run)
    monkeypatch.setattr(parsing, "_preprocess_image_for_ocr", lambda *_args: None)
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
        parsing.importlib,
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

    monkeypatch.setattr(parsing.shutil, "which", lambda command: None)
    monkeypatch.setattr(
        parsing,
        "markitdown_openai_image_options",
        lambda: (_ for _ in ()).throw(parsing.MiaUnavailable("OpenAI is not configured")),
    )
    monkeypatch.setattr(
        parsing.importlib,
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

    monkeypatch.setattr(parsing.shutil, "which", lambda command: None)
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
        parsing.importlib,
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

    monkeypatch.setattr(parsing.importlib, "import_module", missing_module)

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
        commands.append(args)
        Path(args[-1]).write_bytes(b"low quality mp3")
        return SimpleNamespace(returncode=0, stdout="", stderr="encoded")

    monkeypatch.setattr(parsing.shutil, "which", lambda command: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(parsing.subprocess, "run", fake_run)
    monkeypatch.setattr(
        parsing.importlib,
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
        commands.append(args)
        if "segment" in args:
            chunk_dir = Path(args[-1]).parent
            chunk_dir.mkdir(parents=True, exist_ok=True)
            (chunk_dir / "chunk-000.mp3").write_bytes(b"chunk one")
            (chunk_dir / "chunk-001.mp3").write_bytes(b"chunk two")
        else:
            Path(args[-1]).write_bytes(b"low quality mp3")
        return SimpleNamespace(returncode=0, stdout="", stderr="encoded")

    monkeypatch.setattr(parsing.shutil, "which", lambda command: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(parsing.subprocess, "run", fake_run)
    monkeypatch.setattr(
        parsing.importlib,
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
        if "segment" in args:
            chunk_dir = Path(args[-1]).parent
            chunk_dir.mkdir(parents=True, exist_ok=True)
            (chunk_dir / "chunk-000.mp3").write_bytes(b"chunk one")
        else:
            Path(args[-1]).write_bytes(b"low quality mp3")
        return SimpleNamespace(returncode=0, stdout="", stderr="encoded")

    monkeypatch.setattr(parsing.shutil, "which", lambda command: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(parsing.subprocess, "run", fake_run)
    monkeypatch.setattr(
        parsing.importlib,
        "import_module",
        lambda _: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    with pytest.raises(ParserError, match="chunk-000.mp3"):
        parse_document(source)


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
