from __future__ import annotations

from pathlib import Path
from typing import BinaryIO


class UploadTooLargeError(ValueError):
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"Upload exceeds the {max_bytes} byte limit")


class ImageTooLargeError(ValueError):
    def __init__(self, max_pixels: int) -> None:
        self.max_pixels = max_pixels
        super().__init__(f"Image exceeds the {max_pixels} pixel limit")


def copy_stream_with_limit(
    source: BinaryIO,
    destination: BinaryIO,
    *,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> int:
    total = 0
    while True:
        chunk = source.read(chunk_size)
        if not chunk:
            return total
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLargeError(max_bytes)
        destination.write(chunk)


def write_stream_to_path_with_limit(
    source: BinaryIO,
    target: Path,
    *,
    max_bytes: int,
) -> int:
    try:
        with target.open("wb") as destination:
            return copy_stream_with_limit(source, destination, max_bytes=max_bytes)
    except UploadTooLargeError:
        target.unlink(missing_ok=True)
        raise


def read_stream_with_limit(
    source: BinaryIO,
    *,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = source.read(chunk_size)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLargeError(max_bytes)
        chunks.append(chunk)


def ensure_image_pixel_limit(width: int, height: int, *, max_pixels: int) -> None:
    if width * height > max_pixels:
        raise ImageTooLargeError(max_pixels)
