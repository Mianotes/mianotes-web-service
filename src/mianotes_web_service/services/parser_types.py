from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ParserError(RuntimeError):
    pass


class PartialParseError(ParserError):
    def __init__(
        self,
        message: str,
        *,
        partial_text: str,
        partial_failure_message: str,
    ) -> None:
        super().__init__(message)
        self.partial_text = partial_text
        self.partial_failure_message = partial_failure_message


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
