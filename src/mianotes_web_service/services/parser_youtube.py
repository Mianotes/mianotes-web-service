from __future__ import annotations

import html as html_lib
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from mianotes_web_service.services.parser_audio import AUDIO_EXTENSIONS
from mianotes_web_service.services.parser_markdown import normalise_parsed_markdown
from mianotes_web_service.services.parser_markitdown import convert_url_with_markitdown
from mianotes_web_service.services.parser_runtime import log_parser_command
from mianotes_web_service.services.parser_tools import (
    run_youtube_downloader,
    youtube_downloader_executable,
)
from mianotes_web_service.services.parser_types import ParsedDocument, ParserError
from mianotes_web_service.services.parser_url import is_youtube_url

ParseDocument = Callable[[Path], ParsedDocument]


def caption_file_to_text(path: Path) -> str:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    text_lines: list[str] = []
    previous = ""
    for line in lines:
        clean = line.strip()
        if not clean:
            continue
        if clean.upper() == "WEBVTT" or clean.startswith(("Kind:", "Language:")):
            continue
        if "-->" in clean:
            continue
        if clean.isdigit():
            continue
        clean = re.sub(r"<[^>]+>", "", clean)
        clean = html_lib.unescape(clean).strip()
        if not clean or clean == previous:
            continue
        text_lines.append(clean)
        previous = clean
    return "\n".join(text_lines).strip()


def parse_youtube_captions_with_downloader(
    url: str,
    work_dir: Path,
) -> ParsedDocument | None:
    executable = youtube_downloader_executable()
    if executable is None:
        return None

    captions_dir = work_dir / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)
    output_template = captions_dir / "%(id)s.%(ext)s"
    command_parts = [
        executable,
        "--no-playlist",
        "--skip-download",
        "--write-sub",
        "--write-auto-sub",
        "--sub-lang",
        "en",
        "--sub-format",
        "vtt",
        "-o",
        str(output_template),
        url,
    ]
    if not run_youtube_downloader(command_parts, timeout=300):
        return None

    caption_paths = sorted([*captions_dir.glob("*.vtt"), *captions_dir.glob("*.srt")])
    for caption_path in caption_paths:
        text = caption_file_to_text(caption_path)
        if text:
            return ParsedDocument(
                text=f"## YouTube transcript\n\n{text}",
                parser="yt-dlp+captions",
                source_path=caption_path,
            )
    log_parser_command("parse yt-dlp captions", "no readable captions found", status="failed")
    return None


def download_youtube_audio(url: str, work_dir: Path) -> Path | None:
    executable = youtube_downloader_executable()
    if executable is None:
        return None

    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_template = audio_dir / "%(id)s.%(ext)s"
    command_parts = [
        executable,
        "--no-playlist",
        "--max-filesize",
        "200m",
        "-f",
        "bestaudio/best",
        "-o",
        str(output_template),
        url,
    ]
    if not run_youtube_downloader(command_parts, timeout=900):
        return None

    audio_paths = sorted(
        path
        for path in audio_dir.iterdir()
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )
    if not audio_paths:
        log_parser_command("find yt-dlp audio", "no supported audio file found", status="failed")
        return None
    return audio_paths[0]


def parse_youtube_audio_with_downloader(
    url: str,
    work_dir: Path,
    *,
    parse_document: ParseDocument,
) -> ParsedDocument | None:
    audio_path = download_youtube_audio(url, work_dir)
    if audio_path is None:
        return None
    parsed = parse_document(audio_path)
    if not parsed.text.strip():
        return None
    return ParsedDocument(
        text=parsed.text,
        parser=f"{parsed.parser}+yt-dlp-audio",
        source_path=audio_path,
    )


def parse_youtube_url(url: str, *, parse_document: ParseDocument) -> ParsedDocument:
    if not is_youtube_url(url):
        raise ParserError("URL is not a supported YouTube video URL.")
    errors: list[str] = []
    try:
        text = normalise_parsed_markdown(convert_url_with_markitdown(url))
        if text.strip() and "### Transcript" in text:
            return ParsedDocument(
                text=text,
                parser="markitdown+youtube",
                source_path=Path(url),
            )
        errors.append("MarkItDown did not return a YouTube transcript.")
    except ParserError as exc:
        errors.append(str(exc))

    with tempfile.TemporaryDirectory(prefix="mianotes-youtube-") as temp_dir:
        work_dir = Path(temp_dir)
        parsed = parse_youtube_captions_with_downloader(url, work_dir)
        if parsed is not None:
            return ParsedDocument(
                text=parsed.text,
                parser=parsed.parser,
                source_path=Path(url),
            )
        parsed = parse_youtube_audio_with_downloader(url, work_dir, parse_document=parse_document)
        if parsed is not None:
            return ParsedDocument(
                text=parsed.text,
                parser=parsed.parser,
                source_path=Path(url),
            )

    detail = " ".join(errors)
    raise ParserError(
        (
            "Could not extract a YouTube transcript. YouTube may be rate-limiting "
            "transcript requests, this video may not have captions available, or yt-dlp "
            "could not download a fallback."
        )
        + (f" {detail}" if detail else "")
    )
