from pathlib import Path

import pytest

from mianotes_web_service.services.parsing import (
    ParserError,
    ParserRegistry,
    ParserUnavailable,
    PdfTextParser,
    PlainTextParser,
    parse_document,
)


def test_plain_text_parser_reads_markdown(tmp_path: Path):
    source = tmp_path / "note.md"
    source.write_text("# Hello\n\nMianotes parser layer.", encoding="utf-8")

    parsed = parse_document(source)

    assert parsed.parser == "plain-text"
    assert parsed.source_path == source
    assert "Mianotes parser layer" in parsed.text


def test_registry_rejects_unsupported_file(tmp_path: Path):
    source = tmp_path / "archive.zip"
    source.write_text("nope", encoding="utf-8")

    with pytest.raises(ParserError, match="Unsupported file type"):
        ParserRegistry().parse(source)


def test_command_parser_reports_missing_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "file.pdf"
    source.write_bytes(b"%PDF")
    monkeypatch.setattr("mianotes_web_service.services.parsing.shutil.which", lambda _: None)

    with pytest.raises(ParserUnavailable, match="pdftotext is not installed"):
        PdfTextParser().parse(source)


def test_registry_can_be_overridden_for_unit_tests(tmp_path: Path):
    source = tmp_path / "note.md"
    source.write_text("hello", encoding="utf-8")
    registry = ParserRegistry(parsers=[PlainTextParser()])

    assert registry.parse(source).text == "hello"
