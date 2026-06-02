from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from mianotes_web_service.core.config import get_settings
from mianotes_web_service.services.parser_markdown import normalise_ocr_text
from mianotes_web_service.services.parser_runtime import (
    log_parser_command,
    subprocess_response,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
OCR_MIN_CHARACTERS = 20
TESSERACT_CANDIDATES = (
    "tesseract",
    "/opt/homebrew/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/usr/bin/tesseract",
)


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def tesseract_executable() -> str | None:
    try:
        configured_candidates = tuple(get_settings().binaries.get("tesseract", []))
    except Exception:
        configured_candidates = ()
    candidates = configured_candidates or TESSERACT_CANDIDATES

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if "/" in candidate:
            path_candidate = candidate if Path(candidate).is_file() else None
            log_parser_command(f"check executable {candidate}", path_candidate or "not found")
        else:
            path_candidate = shutil.which(candidate)
            log_parser_command(f"shutil.which('{candidate}')", path_candidate or "not found")
        if not path_candidate:
            continue
        command = shlex.join([path_candidate, "--version"])
        try:
            completed = subprocess.run(
                [path_candidate, "--version"],
                capture_output=True,
                check=False,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError, TimeoutError):
            log_parser_command(command, "could not run version check", status="failed")
            continue
        log_parser_command(
            command,
            subprocess_response(completed),
            status="succeeded" if completed.returncode == 0 else "failed",
        )
        if completed.returncode == 0:
            return path_candidate
    log_parser_command("find tesseract executable", "no working executable found", status="failed")
    return None


def run_tesseract(executable: str, path: Path, *, psm: str) -> str | None:
    command_parts = [executable, str(path), "stdout", "--psm", psm]
    command = shlex.join(command_parts)
    try:
        completed = subprocess.run(
            command_parts,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        log_parser_command(command, "command failed or timed out", status="failed")
        return None

    if completed.returncode != 0:
        log_parser_command(command, subprocess_response(completed), status="failed")
        return None

    text = normalise_ocr_text(re.sub(r"\n{3,}", "\n\n", completed.stdout))
    if len(text) < OCR_MIN_CHARACTERS:
        log_parser_command(
            command,
            f"{subprocess_response(completed)}\n\nignored: only {len(text)} readable characters",
            status="failed",
        )
        return None
    log_parser_command(
        command,
        f"{subprocess_response(completed)}\n\naccepted: {len(text)} readable characters",
        status="succeeded",
    )
    return text


def preprocess_image_for_ocr(source_path: Path, output_path: Path) -> Path | None:
    command = f"Pillow preprocess image {source_path.name}"
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ModuleNotFoundError:
        log_parser_command(command, "Pillow is not installed", status="failed")
        return None

    try:
        with Image.open(source_path) as image:
            image = ImageOps.grayscale(image)
            image = ImageOps.autocontrast(image)
            image = ImageEnhance.Sharpness(image).enhance(1.8)
            if max(image.size) < 2400:
                image = image.resize((image.width * 2, image.height * 2))
            image.save(output_path)
    except OSError:
        log_parser_command(command, "could not preprocess image", status="failed")
        return None
    log_parser_command(command, f"wrote {output_path.name}", status="succeeded")
    return output_path


def tesseract_ocr(path: Path) -> str | None:
    executable = tesseract_executable()
    if executable is None:
        return None

    attempts: list[str] = []
    for psm in ("6", "11"):
        text = run_tesseract(executable, path, psm=psm)
        if text:
            attempts.append(text)

    with tempfile.TemporaryDirectory(prefix="mianotes-ocr-") as temp_dir:
        processed_path = preprocess_image_for_ocr(path, Path(temp_dir) / "image.png")
        if processed_path is not None:
            for psm in ("6", "11"):
                text = run_tesseract(executable, processed_path, psm=psm)
                if text:
                    attempts.append(text)

    if not attempts:
        return None
    return max(attempts, key=len)
