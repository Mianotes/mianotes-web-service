from __future__ import annotations

import importlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


def _markitdown_class():
    try:
        module = importlib.import_module("markitdown")
    except ModuleNotFoundError as exc:
        raise ParserUnavailable("markitdown is not installed") from exc
    return module.MarkItDown


class MarkItDownParser:
    name = "markitdown"

    def parse(self, path: Path) -> ParsedDocument:
        if not path.is_file():
            raise ParserError("Source file not found")
        converter = _markitdown_class()()
        try:
            result = converter.convert(str(path))
        except Exception as exc:
            raise ParserError(str(exc)) from exc
        return ParsedDocument(text=result.text_content, parser=self.name, source_path=path)


class ParserRegistry:
    def __init__(self, parser: DocumentParser | None = None) -> None:
        self.parser = parser or MarkItDownParser()

    def parse(self, path: Path) -> ParsedDocument:
        return self.parser.parse(path)


def parse_document(path: Path) -> ParsedDocument:
    return ParserRegistry().parse(path)


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
    return parse_document(html_path)
