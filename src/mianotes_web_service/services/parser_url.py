from __future__ import annotations

import importlib
import ipaddress
import re
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from mianotes_web_service.core.config import get_settings
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
REMOTE_FILE_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".md",
    ".markdown",
    ".mp3",
    ".odt",
    ".pdf",
    ".png",
    ".rtf",
    ".tif",
    ".tiff",
    ".txt",
    ".wav",
}
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
READ_CHUNK_BYTES = 1024 * 1024


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):  # type: ignore[override]
        return None


_URL_OPENER = build_opener(NoRedirectHandler)


def _open_url(request: Request, *, timeout: int):
    return _URL_OPENER.open(request, timeout=timeout)


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


def url_source_extension(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    extension = Path(parsed.path).suffix.lower()
    if extension in REMOTE_FILE_EXTENSIONS:
        return extension
    return None


def _resolve_host_addresses(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return [ipaddress.ip_address(hostname)]
    except ValueError:
        pass

    try:
        results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ParserError(f"Could not resolve URL host: {hostname}") from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for result in results:
        address = result[4][0]
        try:
            parsed_address = ipaddress.ip_address(address)
        except ValueError:
            continue
        if parsed_address not in addresses:
            addresses.append(parsed_address)
    if not addresses:
        raise ParserError(f"Could not resolve URL host: {hostname}")
    return addresses


def validate_fetch_url(url: str) -> None:
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ParserError("URL is not valid.") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ParserError("Only HTTP and HTTPS URLs can be imported.")
    if not parsed.hostname:
        raise ParserError("URL host is required.")

    addresses = _resolve_host_addresses(parsed.hostname)
    if any(not address.is_global for address in addresses):
        raise ParserError("URL host is not allowed.")


def _response_content_length(response) -> int | None:
    value = response.headers.get("Content-Length") if hasattr(response, "headers") else None
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def fetch_url_to_file(
    url: str,
    output_path: Path,
    *,
    user_agent: str = DEFAULT_BROWSER_USER_AGENT,
    timeout: int = 30,
    max_bytes: int | None = None,
) -> Path:
    if max_bytes is None:
        max_bytes = get_settings().max_url_fetch_bytes

    output_path.parent.mkdir(parents=True, exist_ok=True)
    current_url = url
    command = f"GET {current_url}"
    try:
        for _redirect_count in range(MAX_REDIRECTS + 1):
            validate_fetch_url(current_url)
            command = f"GET {current_url}"
            request = Request(current_url, headers={"User-Agent": user_agent})
            try:
                with _open_url(request, timeout=timeout) as response:
                    get_response_url = getattr(response, "geturl", None)
                    response_url = (
                        get_response_url() if callable(get_response_url) else current_url
                    )
                    validate_fetch_url(response_url)
                    content_length = _response_content_length(response)
                    if content_length is not None and content_length > max_bytes:
                        raise ParserError("URL response is too large.")

                    total_bytes = 0
                    with output_path.open("wb") as output:
                        while True:
                            chunk = response.read(READ_CHUNK_BYTES)
                            if not chunk:
                                break
                            total_bytes += len(chunk)
                            if total_bytes > max_bytes:
                                raise ParserError("URL response is too large.")
                            output.write(chunk)

                    log_parser_command(
                        command,
                        f"saved {total_bytes} bytes to {output_path.name}",
                        status="succeeded",
                    )
                    return output_path
            except HTTPError as exc:
                if exc.code not in REDIRECT_STATUS_CODES:
                    raise
                location = exc.headers.get("Location")
                if not location:
                    raise ParserError("URL redirect is missing a destination.") from exc
                current_url = urljoin(current_url, location)
        raise ParserError("URL has too many redirects.")
    except (HTTPError, URLError, TimeoutError, ParserError) as exc:
        output_path.unlink(missing_ok=True)
        log_parser_command(command, str(exc), status="failed")
        if isinstance(exc, ParserError):
            raise
        raise ParserError(f"Could not fetch URL: {exc}") from exc


def fetch_url_to_html(
    url: str,
    output_path: Path,
    *,
    user_agent: str = DEFAULT_BROWSER_USER_AGENT,
    timeout: int = 30,
    max_bytes: int | None = None,
) -> Path:
    return fetch_url_to_file(
        url,
        output_path,
        user_agent=user_agent,
        timeout=timeout,
        max_bytes=max_bytes,
    )


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
