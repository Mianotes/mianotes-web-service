from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mianotes_web_service.services.mia import MiaUnavailable, markitdown_openai_image_options


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
IMAGE_DESCRIPTION_HEADING = "# Description:"
OCR_MIN_CHARACTERS = 20
IMAGE_NEEDS_CLOUD_MESSAGE = (
    "Sorry, Mia was unable to get any text from this image.\n\n"
    "Please configure a cloud LLM to improve Mia's image reading capabilities."
)
IMAGE_UNREADABLE_MESSAGE = "Sorry, Mia was unable to extract any text from this image."


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


def _normalise_image_markdown(text: str) -> str | None:
    if IMAGE_DESCRIPTION_HEADING not in text:
        return None
    description = text.split(IMAGE_DESCRIPTION_HEADING, 1)[1].strip()
    return description or None


def _convert_with_markitdown(path: Path, **options: object) -> str:
    converter = _markitdown_class()(**options)
    try:
        result = converter.convert(str(path))
    except Exception as exc:
        raise ParserError(str(exc)) from exc
    return result.text_content


def _tesseract_ocr(path: Path) -> str | None:
    if shutil.which("tesseract") is None:
        return None

    try:
        completed = subprocess.run(
            ["tesseract", str(path), "stdout"],
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        return None

    if completed.returncode != 0:
        return None

    text = re.sub(r"\n{3,}", "\n\n", completed.stdout).strip()
    if len(text) < OCR_MIN_CHARACTERS:
        return None
    return text


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

        return ParsedDocument(
            text=_convert_with_markitdown(path),
            parser=self.name,
            source_path=path,
        )

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
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ParserError(f"Could not fetch URL: {exc}") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
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
