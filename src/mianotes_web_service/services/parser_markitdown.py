from __future__ import annotations

import importlib
from pathlib import Path

from mianotes_web_service.services.parser_runtime import log_parser_command
from mianotes_web_service.services.parser_types import ParserError, ParserUnavailable


def markitdown_class():
    try:
        module = importlib.import_module("markitdown")
    except ModuleNotFoundError as exc:
        raise ParserUnavailable("markitdown is not installed") from exc
    return module.MarkItDown


def convert_with_markitdown(path: Path, **options: object) -> str:
    command = f"MarkItDown.convert({path.name})"
    if options:
        command = f"{command} with plugins/options"
    log_parser_command(command, "started", status="running")
    converter = markitdown_class()(**options)
    try:
        result = converter.convert(str(path))
    except Exception as exc:
        log_parser_command(command, str(exc), status="failed")
        raise ParserError(str(exc)) from exc
    log_parser_command(
        command,
        f"converted {len(result.text_content)} characters",
        status="succeeded",
    )
    return result.text_content


def convert_url_with_markitdown(url: str) -> str:
    command = f"MarkItDown.convert({url})"
    log_parser_command(command, "started", status="running")
    converter = markitdown_class()()
    try:
        result = converter.convert(url)
    except Exception as exc:
        log_parser_command(command, str(exc), status="failed")
        raise ParserError(str(exc)) from exc
    log_parser_command(
        command,
        f"converted {len(result.text_content)} characters",
        status="succeeded",
    )
    return result.text_content
