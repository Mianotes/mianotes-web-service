from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


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
    supported_extensions: frozenset[str]

    def parse(self, path: Path) -> ParsedDocument:
        pass


def _require_command(command: str) -> str:
    command_path = shutil.which(command)
    if command_path is None:
        raise ParserUnavailable(f"{command} is not installed")
    return command_path


def _run_command(command: list[str], *, input_text: str | None = None) -> str:
    completed = subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise ParserError(completed.stderr.strip() or f"{command[0]} failed")
    return completed.stdout


class PlainTextParser:
    name = "plain-text"
    supported_extensions = frozenset({".md", ".markdown", ".txt"})

    def parse(self, path: Path) -> ParsedDocument:
        return ParsedDocument(
            text=path.read_text(encoding="utf-8"),
            parser=self.name,
            source_path=path,
        )


class PdfTextParser:
    name = "pdftotext"
    supported_extensions = frozenset({".pdf"})

    def parse(self, path: Path) -> ParsedDocument:
        pdftotext = _require_command("pdftotext")
        text = _run_command([pdftotext, str(path), "-"])
        return ParsedDocument(text=text, parser=self.name, source_path=path)


class PandocParser:
    name = "pandoc"
    supported_extensions = frozenset(
        {
            ".doc",
            ".docx",
            ".docm",
            ".html",
            ".htm",
            ".odt",
            ".rtf",
            ".pptx",
            ".csv",
        }
    )

    def parse(self, path: Path) -> ParsedDocument:
        pandoc = _require_command("pandoc")
        text = _run_command([pandoc, str(path), "--to", "markdown", "--wrap", "none"])
        return ParsedDocument(text=text, parser=self.name, source_path=path)


class TesseractParser:
    name = "tesseract"
    supported_extensions = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff"})

    def parse(self, path: Path) -> ParsedDocument:
        tesseract = _require_command("tesseract")
        text = _run_command([tesseract, str(path), "stdout"])
        return ParsedDocument(text=text, parser=self.name, source_path=path)


class MarkdownFormatter:
    name = "mdformat"

    def format(self, text: str) -> str:
        mdformat = _require_command("mdformat")
        return _run_command([mdformat, "-"], input_text=text)


class ParserRegistry:
    def __init__(self, parsers: list[DocumentParser] | None = None) -> None:
        self.parsers = parsers or [
            PlainTextParser(),
            PdfTextParser(),
            PandocParser(),
            TesseractParser(),
        ]

    def parser_for(self, path: Path) -> DocumentParser:
        extension = path.suffix.lower()
        for parser in self.parsers:
            if extension in parser.supported_extensions:
                return parser
        raise ParserError(f"Unsupported file type: {extension or 'unknown'}")

    def parse(self, path: Path) -> ParsedDocument:
        if not path.is_file():
            raise ParserError("Source file not found")
        return self.parser_for(path).parse(path)


def parse_document(path: Path) -> ParsedDocument:
    return ParserRegistry().parse(path)


def format_markdown(text: str) -> str:
    return MarkdownFormatter().format(text)
