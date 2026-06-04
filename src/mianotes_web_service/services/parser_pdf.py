from __future__ import annotations

import tempfile
from pathlib import Path

from mianotes_web_service.services.parser_image import tesseract_executable, tesseract_ocr
from mianotes_web_service.services.parser_runtime import emit_parser_text_update, log_parser_command

PDF_EXTENSIONS = {".pdf"}
PDF_RENDER_ZOOM = 2.0


def is_pdf(path: Path) -> bool:
    return path.suffix.lower() in PDF_EXTENSIONS


def render_pdf_pages_for_ocr(source_path: Path, output_dir: Path) -> list[Path]:
    command = f"PyMuPDF render {source_path.name}"
    try:
        import fitz
    except ModuleNotFoundError:
        log_parser_command(command, "PyMuPDF is not installed", status="failed")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        document = fitz.open(source_path)
    except Exception as exc:
        log_parser_command(command, f"could not open PDF: {exc}", status="failed")
        return []

    rendered_pages: list[Path] = []
    try:
        matrix = fitz.Matrix(PDF_RENDER_ZOOM, PDF_RENDER_ZOOM)
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            page_path = output_dir / f"page-{page_index + 1:04d}.png"
            pixmap.save(page_path)
            rendered_pages.append(page_path)
    except Exception as exc:
        log_parser_command(command, f"could not render PDF pages: {exc}", status="failed")
        return []
    finally:
        document.close()

    log_parser_command(command, f"rendered {len(rendered_pages)} pages", status="succeeded")
    return rendered_pages


def tesseract_pdf_ocr(path: Path) -> str | None:
    executable = tesseract_executable()
    if executable is None:
        return None

    with tempfile.TemporaryDirectory(prefix="mianotes-pdf-ocr-") as temp_dir:
        page_paths = render_pdf_pages_for_ocr(path, Path(temp_dir))
        if not page_paths:
            return None

        page_parts: list[str] = []
        for page_path in page_paths:
            page_text = tesseract_ocr(page_path, executable=executable)
            if not page_text:
                continue
            page_parts.append(page_text)
            emit_parser_text_update("\n\n".join(page_parts))

    if not page_parts:
        log_parser_command("Tesseract PDF OCR", "no readable text found", status="failed")
        return None

    return "\n\n".join(page_parts)
