from __future__ import annotations

import importlib
import re
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mianotes_web_service.services.mia import MiaUnavailable, markitdown_llm_options


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
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
IMAGE_DESCRIPTION_HEADING = "# Description:"


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


def _markitdown_options(path: Path) -> dict[str, object]:
    if not _is_image(path):
        return {}
    try:
        return markitdown_llm_options()
    except MiaUnavailable as exc:
        raise ParserUnavailable(
            "Image parsing needs a configured vision-capable LLM. Set "
            "MIANOTES_LLM_PROVIDER, MIANOTES_LLM_MODEL, and MIANOTES_LLM_API_KEY, "
            "or set MIANOTES_LLM_IMAGE_MODEL to a model that can read images."
        ) from exc


def _normalise_image_markdown(text: str) -> str:
    if IMAGE_DESCRIPTION_HEADING not in text:
        raise ParserError(
            "Image parsing returned metadata only. Configure a vision-capable model "
            "for image uploads, for example by setting MIANOTES_LLM_IMAGE_MODEL."
        )
    return text.split(IMAGE_DESCRIPTION_HEADING, 1)[1].strip()


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
        converter = _markitdown_class()(**_markitdown_options(path))
        try:
            result = converter.convert(str(path))
        except Exception as exc:
            raise ParserError(str(exc)) from exc
        text = result.text_content
        if _is_image(path):
            text = _normalise_image_markdown(text)
        return ParsedDocument(text=text, parser=self.name, source_path=path)


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
