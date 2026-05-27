from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

ParserLogCallback = Callable[[str, str | None, str], None]
ParserTextCallback = Callable[[str], None]
_PARSER_LOGGER: ContextVar[ParserLogCallback | None] = ContextVar(
    "mianotes_parser_logger",
    default=None,
)
_PARSER_TEXT_CALLBACK: ContextVar[ParserTextCallback | None] = ContextVar(
    "mianotes_parser_text_callback",
    default=None,
)


@contextmanager
def parser_job_logging(callback: ParserLogCallback) -> Iterator[None]:
    token = _PARSER_LOGGER.set(callback)
    try:
        yield
    finally:
        _PARSER_LOGGER.reset(token)


@contextmanager
def parser_text_updates(callback: ParserTextCallback) -> Iterator[None]:
    token = _PARSER_TEXT_CALLBACK.set(callback)
    try:
        yield
    finally:
        _PARSER_TEXT_CALLBACK.reset(token)


def log_parser_command(
    command: str,
    response: str | None = None,
    *,
    status: str = "info",
) -> None:
    callback = _PARSER_LOGGER.get()
    if callback is None:
        return
    callback(command, response, status)


def emit_parser_text_update(text: str) -> None:
    callback = _PARSER_TEXT_CALLBACK.get()
    if callback is None:
        return
    callback(text)


def subprocess_response(completed: subprocess.CompletedProcess[str]) -> str:
    parts = [f"exit {completed.returncode}"]
    stdout = (getattr(completed, "stdout", "") or "").strip()
    stderr = (getattr(completed, "stderr", "") or "").strip()
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    return "\n\n".join(parts)
