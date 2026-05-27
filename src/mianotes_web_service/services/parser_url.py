from __future__ import annotations

import importlib
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from mianotes_web_service.services.parser_runtime import log_parser_command
from mianotes_web_service.services.parser_types import ParserError

DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
)
YOUTUBE_HOSTS = {
    "m.youtube.com",
    "music.youtube.com",
    "www.youtube.com",
    "youtube.com",
    "youtu.be",
}


def trafilatura_module():
    try:
        return importlib.import_module("trafilatura")
    except ModuleNotFoundError:
        return None


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self.parts)


def visible_text_length(html: str) -> int:
    parser = HTMLTextExtractor()
    parser.feed(html)
    return len(re.sub(r"\s+", " ", parser.text).strip())


def extract_readable_html(html_path: Path, *, url: str | None = None) -> str | None:
    trafilatura = trafilatura_module()
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

    if not extracted or visible_text_length(extracted) < 80:
        return None
    return f"<!doctype html>\n<html><body>\n{extracted}\n</body></html>\n"


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
        log_parser_command(command, str(exc), status="failed")
        raise ParserError(f"Could not fetch URL: {exc}") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    log_parser_command(
        command,
        f"saved {len(content)} bytes to {output_path.name}",
        status="succeeded",
    )
    return output_path


def is_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return False
    if host == "youtu.be":
        return bool(parsed.path.strip("/"))
    if parsed.path == "/watch":
        return bool(parse_qs(parsed.query).get("v", [""])[0])
    return parsed.path.startswith(("/shorts/", "/embed/", "/live/"))
