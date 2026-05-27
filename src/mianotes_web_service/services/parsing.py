from __future__ import annotations

import tempfile
from pathlib import Path

from mianotes_web_service.services.mia import (
    MiaUnavailable,
    markitdown_llm_options,
    markitdown_openai_image_options,
)
from mianotes_web_service.services.parser_audio import (
    AUDIO_CHUNK_SECONDS as AUDIO_CHUNK_SECONDS,
)
from mianotes_web_service.services.parser_audio import (
    AUDIO_EXTENSIONS as AUDIO_EXTENSIONS,
)
from mianotes_web_service.services.parser_audio import (
    is_audio as _is_audio,
)
from mianotes_web_service.services.parser_audio import (
    split_audio_to_low_quality_mp3_chunks as _split_audio_to_low_quality_mp3_chunks,
)
from mianotes_web_service.services.parser_audio import (
    transcode_audio_to_low_quality_mp3 as _transcode_audio_to_low_quality_mp3,
)
from mianotes_web_service.services.parser_image import (
    IMAGE_EXTENSIONS as IMAGE_EXTENSIONS,
)
from mianotes_web_service.services.parser_image import (
    OCR_MIN_CHARACTERS as OCR_MIN_CHARACTERS,
)
from mianotes_web_service.services.parser_image import (
    TESSERACT_CANDIDATES as TESSERACT_CANDIDATES,
)
from mianotes_web_service.services.parser_image import (
    is_image as _is_image,
)
from mianotes_web_service.services.parser_image import (
    tesseract_ocr as _tesseract_ocr,
)
from mianotes_web_service.services.parser_markdown import (
    IMAGE_DESCRIPTION_HEADING as IMAGE_DESCRIPTION_HEADING,
)
from mianotes_web_service.services.parser_markdown import (
    normalise_image_markdown as _normalise_image_markdown,
)
from mianotes_web_service.services.parser_markdown import (
    normalise_parsed_markdown,
)
from mianotes_web_service.services.parser_markitdown import (
    convert_with_markitdown as _convert_with_markitdown,
)
from mianotes_web_service.services.parser_runtime import (
    emit_parser_text_update as _emit_parser_text_update,
)
from mianotes_web_service.services.parser_runtime import (
    log_parser_command as _log_parser_command,
)
from mianotes_web_service.services.parser_runtime import (
    parser_job_logging as parser_job_logging,
)
from mianotes_web_service.services.parser_runtime import (
    parser_text_updates as parser_text_updates,
)
from mianotes_web_service.services.parser_tools import (
    AUDIO_TOOL_DIR_CANDIDATES as AUDIO_TOOL_DIR_CANDIDATES,
)
from mianotes_web_service.services.parser_tools import (
    AUDIO_TOOL_NAMES as AUDIO_TOOL_NAMES,
)
from mianotes_web_service.services.parser_tools import (
    AUDIO_TOOL_VERSION_ARGS as AUDIO_TOOL_VERSION_ARGS,
)
from mianotes_web_service.services.parser_tools import (
    FFMPEG_CANDIDATES as FFMPEG_CANDIDATES,
)
from mianotes_web_service.services.parser_tools import (
    YOUTUBE_DOWNLOADER_CANDIDATES as YOUTUBE_DOWNLOADER_CANDIDATES,
)
from mianotes_web_service.services.parser_tools import (
    prefer_working_audio_tools as _prefer_working_audio_tools,
)
from mianotes_web_service.services.parser_types import (
    DocumentParser,
    ParsedDocument,
    ParserError,
)
from mianotes_web_service.services.parser_types import (
    ParserUnavailable as ParserUnavailable,
)
from mianotes_web_service.services.parser_url import (
    DEFAULT_BROWSER_USER_AGENT,
    fetch_url_to_html,
)
from mianotes_web_service.services.parser_url import (
    YOUTUBE_HOSTS as YOUTUBE_HOSTS,
)
from mianotes_web_service.services.parser_url import (
    extract_readable_html as _extract_readable_html,
)
from mianotes_web_service.services.parser_url import (
    is_youtube_url as is_youtube_url,
)
from mianotes_web_service.services.parser_youtube import (
    parse_youtube_audio_with_downloader,
)
from mianotes_web_service.services.parser_youtube import (
    parse_youtube_url as _parse_youtube_url,
)

IMAGE_NEEDS_CLOUD_MESSAGE = (
    "Mia couldn't read the text in this image.\n\n"
    "To help Mia read images, screenshots, and scanned documents, connect Mia to "
    "a local or cloud AI model, then upload it again."
)
IMAGE_UNREADABLE_MESSAGE = (
    "Mia couldn't read the text in this image.\n\n"
    "To help Mia read images, screenshots, and scanned documents, connect Mia to "
    "a local or cloud AI model, then upload it again."
)
DOCUMENT_UNREADABLE_MESSAGE = (
    "Mia couldn't read the text in this file.\n\n"
    "Some files are saved as pictures instead of selectable text. To read files "
    "like this, connect Mia to a local or cloud AI model, then upload the file again."
)
NO_AUDIO_SPEECH_MESSAGE = "Mia could not detect speech in the audio."


def _is_audio_not_understood_error(exc: ParserError) -> bool:
    return "UnknownValueError" in str(exc)


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
        with _prefer_working_audio_tools():
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
            try:
                text = normalise_parsed_markdown(_convert_with_markitdown(converted_path))
            except ParserError:
                text = ""
            if text.strip():
                return text

            chunks = _split_audio_to_low_quality_mp3_chunks(path, Path(temp_dir) / "chunks")
            if not chunks:
                raise ParserError(NO_AUDIO_SPEECH_MESSAGE)

            transcript_parts: list[str] = []
            for index, chunk_path in enumerate(chunks, start=1):
                try:
                    chunk_text = normalise_parsed_markdown(_convert_with_markitdown(chunk_path))
                except ParserError as exc:
                    if _is_audio_not_understood_error(exc):
                        _log_parser_command(
                            f"skip {chunk_path.name}",
                            NO_AUDIO_SPEECH_MESSAGE,
                        )
                        continue
                    raise ParserError(
                        f"Audio chunk transcription failed for {chunk_path.name}: {exc}"
                    ) from exc
                if chunk_text.strip():
                    transcript_parts.append(f"### Part {index}\n\n{chunk_text}")
                    _emit_parser_text_update(
                        "## Audio transcript\n\n" + "\n\n".join(transcript_parts)
                    )

            if transcript_parts:
                return "## Audio transcript\n\n" + "\n\n".join(transcript_parts)
        raise ParserError(NO_AUDIO_SPEECH_MESSAGE)

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


def _parse_youtube_audio_with_downloader(url: str, work_dir: Path) -> ParsedDocument | None:
    return parse_youtube_audio_with_downloader(url, work_dir, parse_document=parse_document)


def parse_youtube_url(url: str) -> ParsedDocument:
    return _parse_youtube_url(url, parse_document=parse_document)


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
