from __future__ import annotations

import importlib
import re
import shlex
import shutil
import subprocess
import tempfile
import textwrap
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mianotes_web_service.services.mia import (
    MiaUnavailable,
    markitdown_llm_options,
    markitdown_openai_image_options,
)


class ParserError(RuntimeError):
    pass


class ParserUnavailable(ParserError):
    pass


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    parser: str
    source_path: Path


class DocumentParser(Protocol):
    name: str

    def parse(self, path: Path) -> ParsedDocument:
        pass


DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
AUDIO_EXTENSIONS = {".aac", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".webm"}
IMAGE_DESCRIPTION_HEADING = "# Description:"
OCR_MIN_CHARACTERS = 20
FENCED_CODE_BLOCK_PATTERN = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)
MARKITDOWN_OCR_BLOCK_PATTERN = re.compile(
    r"\*?\[Image OCR\]\s*"
    r"```(?:markdown|md|text)?\s*\n"
    r"(?P<body>.*?)"
    r"\n```\s*"
    r"\[End OCR\]\*?",
    re.IGNORECASE | re.DOTALL,
)
MARKITDOWN_OCR_MARKER_LINE_PATTERN = re.compile(
    r"^\*?\[(?:Image OCR|End OCR)\]\*?\s*\n?",
    re.IGNORECASE | re.MULTILINE,
)
HTML_VOID_TAG_PATTERN = re.compile(
    r"<(?P<tag>area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)"
    r"(?P<attrs>\s[^<>]*?)?\s*/?>",
    re.IGNORECASE,
)
IMAGE_NEEDS_CLOUD_MESSAGE = (
    "Mia couldn’t read the text in this image.\n\n"
    "To help Mia read images, screenshots, and scanned documents, connect Mia to "
    "a local or cloud AI model, then upload it again."
)
IMAGE_UNREADABLE_MESSAGE = (
    "Mia couldn’t read the text in this image.\n\n"
    "To help Mia read images, screenshots, and scanned documents, connect Mia to "
    "a local or cloud AI model, then upload it again."
)
DOCUMENT_UNREADABLE_MESSAGE = (
    "Mia couldn’t read the text in this file.\n\n"
    "Some files are saved as pictures instead of selectable text. To read files "
    "like this, connect Mia to a local or cloud AI model, then upload the file again."
)
TESSERACT_CANDIDATES = (
    "/opt/homebrew/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/usr/bin/tesseract",
)
ParserLogCallback = Callable[[str, str | None, str], None]
_PARSER_LOGGER: ContextVar[ParserLogCallback | None] = ContextVar(
    "mianotes_parser_logger",
    default=None,
)


@contextmanager
def parser_job_logging(callback: ParserLogCallback) -> Iterator[None]:
    token = _PARSER_LOGGER.set(callback)
    try:
        yield
    finally:
        _PARSER_LOGGER.reset(token)


def _log_parser_command(
    command: str,
    response: str | None = None,
    *,
    status: str = "info",
) -> None:
    callback = _PARSER_LOGGER.get()
    if callback is None:
        return
    callback(command, response, status)


def _subprocess_response(completed: subprocess.CompletedProcess[str]) -> str:
    parts = [f"exit {completed.returncode}"]
    stdout = (getattr(completed, "stdout", "") or "").strip()
    stderr = (getattr(completed, "stderr", "") or "").strip()
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    return "\n\n".join(parts)


def _markitdown_class():
    try:
        module = importlib.import_module("markitdown")
    except ModuleNotFoundError as exc:
        raise ParserUnavailable("markitdown is not installed") from exc
    return module.MarkItDown


def _trafilatura_module():
    try:
        return importlib.import_module("trafilatura")
    except ModuleNotFoundError:
        return None


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def _is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def _normalise_image_markdown(text: str) -> str | None:
    if IMAGE_DESCRIPTION_HEADING not in text:
        return None
    description = text.split(IMAGE_DESCRIPTION_HEADING, 1)[1].strip()
    description = _strip_outer_markdown_fence(description)
    return description or None


def _strip_outer_markdown_fence(text: str) -> str:
    match = re.fullmatch(
        r"```(?:markdown|md|text)?\s*\n(?P<body>.*?)\n```",
        text.strip(),
        re.DOTALL,
    )
    if match is None:
        return text.strip()
    return match.group("body").strip()


def _normalise_ocr_text(text: str) -> str:
    text = _strip_outer_markdown_fence(text)
    text = textwrap.dedent(text).strip()
    lines = [line.rstrip() for line in text.splitlines()]
    if not lines:
        return ""

    indented_lines = [line for line in lines if line.startswith(("    ", "\t"))]
    non_empty_lines = [line for line in lines if line.strip()]
    if non_empty_lines and len(indented_lines) / len(non_empty_lines) >= 0.5:
        lines = [line.lstrip() if line.strip() else line for line in lines]

    return "\n".join(lines).strip()


def _normalise_document_ocr_markdown(text: str) -> str:
    def replace_block(match: re.Match[str]) -> str:
        return f"\n\n{_strip_outer_markdown_fence(match.group('body'))}\n\n"

    cleaned, replacements = MARKITDOWN_OCR_BLOCK_PATTERN.subn(replace_block, text)
    cleaned, marker_replacements = MARKITDOWN_OCR_MARKER_LINE_PATTERN.subn("", cleaned)
    if replacements == 0 and marker_replacements == 0:
        return text

    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _normalise_html_void_tags(text: str) -> str:
    def replace_tag(match: re.Match[str]) -> str:
        attrs = (match.group("attrs") or "").rstrip()
        return f"<{match.group('tag').lower()}{attrs} />"

    parts = FENCED_CODE_BLOCK_PATTERN.split(text)
    for index, part in enumerate(parts):
        if index % 2 == 0:
            parts[index] = HTML_VOID_TAG_PATTERN.sub(replace_tag, part)
    return "".join(parts)


def normalise_parsed_markdown(text: str) -> str:
    return _normalise_html_void_tags(_normalise_document_ocr_markdown(text))


def _convert_with_markitdown(path: Path, **options: object) -> str:
    command = f"MarkItDown.convert({path.name})"
    if options:
        command = f"{command} with plugins/options"
    _log_parser_command(command, "started", status="running")
    converter = _markitdown_class()(**options)
    try:
        result = converter.convert(str(path))
    except Exception as exc:
        _log_parser_command(command, str(exc), status="failed")
        raise ParserError(str(exc)) from exc
    _log_parser_command(
        command,
        f"converted {len(result.text_content)} characters",
        status="succeeded",
    )
    return result.text_content


def _ffmpeg_executable() -> str | None:
    path_candidate = shutil.which("ffmpeg")
    _log_parser_command("shutil.which('ffmpeg')", path_candidate or "not found")
    if path_candidate:
        return path_candidate
    return None


def _transcode_audio_to_low_quality_mp3(source_path: Path, output_path: Path) -> Path | None:
    executable = _ffmpeg_executable()
    if executable is None:
        return None

    command_parts = [
        executable,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "32k",
        str(output_path),
    ]
    command = shlex.join(command_parts)
    _log_parser_command(command, "started", status="running")
    try:
        completed = subprocess.run(
            command_parts,
            capture_output=True,
            check=False,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        _log_parser_command(command, "command failed or timed out", status="failed")
        return None

    if completed.returncode != 0 or not output_path.is_file():
        _log_parser_command(command, _subprocess_response(completed), status="failed")
        return None

    _log_parser_command(
        command,
        f"{_subprocess_response(completed)}\n\nwrote {output_path.name}",
        status="succeeded",
    )
    return output_path


def _tesseract_executable() -> str | None:
    candidates: list[str] = []
    path_candidate = shutil.which("tesseract")
    _log_parser_command("shutil.which('tesseract')", path_candidate or "not found")
    if path_candidate:
        candidates.append(path_candidate)
    candidates.extend(TESSERACT_CANDIDATES)

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen or not Path(candidate).is_file():
            continue
        seen.add(candidate)
        command = shlex.join([candidate, "--version"])
        try:
            completed = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                check=False,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError, TimeoutError):
            _log_parser_command(command, "could not run version check", status="failed")
            continue
        _log_parser_command(
            command,
            _subprocess_response(completed),
            status="succeeded" if completed.returncode == 0 else "failed",
        )
        if completed.returncode == 0:
            return candidate
    _log_parser_command("find tesseract executable", "no working executable found", status="failed")
    return None


def _run_tesseract(executable: str, path: Path, *, psm: str) -> str | None:
    command_parts = [executable, str(path), "stdout", "--psm", psm]
    command = shlex.join(command_parts)
    try:
        completed = subprocess.run(
            command_parts,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        _log_parser_command(command, "command failed or timed out", status="failed")
        return None

    if completed.returncode != 0:
        _log_parser_command(command, _subprocess_response(completed), status="failed")
        return None

    text = _normalise_ocr_text(re.sub(r"\n{3,}", "\n\n", completed.stdout))
    if len(text) < OCR_MIN_CHARACTERS:
        _log_parser_command(
            command,
            f"{_subprocess_response(completed)}\n\nignored: only {len(text)} readable characters",
            status="failed",
        )
        return None
    _log_parser_command(
        command,
        f"{_subprocess_response(completed)}\n\naccepted: {len(text)} readable characters",
        status="succeeded",
    )
    return text


def _preprocess_image_for_ocr(source_path: Path, output_path: Path) -> Path | None:
    command = f"Pillow preprocess image {source_path.name}"
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ModuleNotFoundError:
        _log_parser_command(command, "Pillow is not installed", status="failed")
        return None

    try:
        with Image.open(source_path) as image:
            image = ImageOps.grayscale(image)
            image = ImageOps.autocontrast(image)
            image = ImageEnhance.Sharpness(image).enhance(1.8)
            if max(image.size) < 2400:
                image = image.resize((image.width * 2, image.height * 2))
            image.save(output_path)
    except OSError:
        _log_parser_command(command, "could not preprocess image", status="failed")
        return None
    _log_parser_command(command, f"wrote {output_path.name}", status="succeeded")
    return output_path


def _tesseract_ocr(path: Path) -> str | None:
    executable = _tesseract_executable()
    if executable is None:
        return None

    attempts: list[str] = []
    for psm in ("6", "11"):
        text = _run_tesseract(executable, path, psm=psm)
        if text:
            attempts.append(text)

    with tempfile.TemporaryDirectory(prefix="mianotes-ocr-") as temp_dir:
        processed_path = _preprocess_image_for_ocr(path, Path(temp_dir) / "image.png")
        if processed_path is not None:
            for psm in ("6", "11"):
                text = _run_tesseract(executable, processed_path, psm=psm)
                if text:
                    attempts.append(text)

    if not attempts:
        return None
    return max(attempts, key=len)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self.parts)


def _visible_text_length(html: str) -> int:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return len(re.sub(r"\s+", " ", parser.text).strip())


def _extract_readable_html(html_path: Path, *, url: str | None = None) -> str | None:
    trafilatura = _trafilatura_module()
    if trafilatura is None:
        return None

    html = html_path.read_text(encoding="utf-8", errors="ignore")
    try:
        extracted = trafilatura.extract(
            html,
            url=url,
            output_format="html",
            include_comments=False,
            include_images=True,
            include_links=True,
            include_tables=True,
        )
    except TypeError:
        extracted = trafilatura.extract(html, url=url, output_format="html")
    except Exception:
        return None

    if not extracted or _visible_text_length(extracted) < 80:
        return None
    return f"<!doctype html>\n<html><body>\n{extracted}\n</body></html>\n"


class MarkItDownParser:
    name = "markitdown"

    def parse(self, path: Path) -> ParsedDocument:
        if not path.is_file():
            raise ParserError("Source file not found")
        if _is_image(path):
            return self._parse_image(path)
        if _is_audio(path):
            return self._parse_audio(path)

        text = normalise_parsed_markdown(_convert_with_markitdown(path))
        if text.strip():
            return ParsedDocument(
                text=text,
                parser=self.name,
                source_path=path,
            )

        return ParsedDocument(
            text=self._parse_document_with_ocr(path),
            parser="markitdown+ocr",
            source_path=path,
        )

    def _parse_document_with_ocr(self, path: Path) -> str:
        try:
            text = _convert_with_markitdown(
                path,
                enable_plugins=True,
                **markitdown_llm_options(),
            )
        except MiaUnavailable:
            return DOCUMENT_UNREADABLE_MESSAGE
        text = normalise_parsed_markdown(text)
        return text if text.strip() else DOCUMENT_UNREADABLE_MESSAGE

    def _parse_audio(self, path: Path) -> ParsedDocument:
        try:
            text = normalise_parsed_markdown(_convert_with_markitdown(path))
        except ParserError:
            text = self._parse_low_quality_audio(path)
            return ParsedDocument(
                text=text,
                parser="markitdown+ffmpeg-mp3",
                source_path=path,
            )

        if text.strip():
            return ParsedDocument(
                text=text,
                parser=self.name,
                source_path=path,
            )

        text = self._parse_low_quality_audio(path)
        return ParsedDocument(
            text=text,
            parser="markitdown+ffmpeg-mp3",
            source_path=path,
        )

    def _parse_low_quality_audio(self, path: Path) -> str:
        with tempfile.TemporaryDirectory(prefix="mianotes-audio-") as temp_dir:
            mp3_path = Path(temp_dir) / "low-quality.mp3"
            converted_path = _transcode_audio_to_low_quality_mp3(path, mp3_path)
            if converted_path is None:
                raise ParserError("Could not convert audio to a low quality MP3 fallback.")
            text = normalise_parsed_markdown(_convert_with_markitdown(converted_path))
            if text.strip():
                return text
        raise ParserError("Audio conversion produced no transcript.")

    def _parse_image(self, path: Path) -> ParsedDocument:
        _convert_with_markitdown(path)

        ocr_text = _tesseract_ocr(path)
        if ocr_text:
            return ParsedDocument(text=ocr_text, parser="markitdown+tesseract", source_path=path)

        try:
            image_text = _normalise_image_markdown(
                _convert_with_markitdown(path, **markitdown_openai_image_options())
            )
        except MiaUnavailable:
            return ParsedDocument(
                text=IMAGE_NEEDS_CLOUD_MESSAGE,
                parser="markitdown+tesseract",
                source_path=path,
            )
        except ParserError:
            image_text = None

        if image_text:
            return ParsedDocument(
                text=image_text,
                parser="markitdown+tesseract+openai",
                source_path=path,
            )

        return ParsedDocument(
            text=IMAGE_UNREADABLE_MESSAGE,
            parser="markitdown+tesseract+openai",
            source_path=path,
        )


class ParserRegistry:
    def __init__(self, parser: DocumentParser | None = None) -> None:
        self.parser = parser or MarkItDownParser()

    def parse(self, path: Path) -> ParsedDocument:
        return self.parser.parse(path)


def parse_document(path: Path) -> ParsedDocument:
    return ParserRegistry().parse(path)


def parse_html_document(path: Path, *, url: str | None = None) -> ParsedDocument:
    cleaned_html = _extract_readable_html(path, url=url)
    if cleaned_html is None:
        return parse_document(path)

    with tempfile.TemporaryDirectory(prefix="mianotes-clean-html-") as temp_dir:
        cleaned_path = Path(temp_dir) / "page.content.html"
        cleaned_path.write_text(cleaned_html, encoding="utf-8")
        parsed = parse_document(cleaned_path)
        return ParsedDocument(
            text=parsed.text,
            parser=f"{parsed.parser}+trafilatura",
            source_path=path,
        )


def fetch_url_to_html(
    url: str,
    output_path: Path,
    *,
    user_agent: str = DEFAULT_BROWSER_USER_AGENT,
    timeout: int = 30,
) -> Path:
    request = Request(url, headers={"User-Agent": user_agent})
    command = f"GET {url}"
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        _log_parser_command(command, str(exc), status="failed")
        raise ParserError(f"Could not fetch URL: {exc}") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    _log_parser_command(
        command,
        f"saved {len(content)} bytes to {output_path.name}",
        status="succeeded",
    )
    return output_path


def parse_url(
    url: str,
    *,
    work_dir: Path | None = None,
    user_agent: str = DEFAULT_BROWSER_USER_AGENT,
) -> ParsedDocument:
    if work_dir is None:
        with tempfile.TemporaryDirectory(prefix="mianotes-url-") as temp_dir:
            return parse_url(url, work_dir=Path(temp_dir), user_agent=user_agent)
    html_path = fetch_url_to_html(url, work_dir / "page.html", user_agent=user_agent)
    return parse_html_document(html_path, url=url)
