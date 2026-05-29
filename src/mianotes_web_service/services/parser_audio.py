from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from mianotes_web_service.services.parser_runtime import (
    log_parser_command,
    subprocess_response,
)
from mianotes_web_service.services.parser_tools import ffmpeg_executable

AUDIO_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
}
AUDIO_CHUNK_SECONDS = 300


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def transcode_audio_to_low_quality_mp3(source_path: Path, output_path: Path) -> Path | None:
    executable = ffmpeg_executable()
    if executable is None:
        return None

    command_parts = [
        executable,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "32k",
        str(output_path),
    ]
    command = shlex.join(command_parts)
    log_parser_command(command, "started", status="running")
    try:
        completed = subprocess.run(
            command_parts,
            capture_output=True,
            check=False,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        log_parser_command(command, "command failed or timed out", status="failed")
        return None

    if completed.returncode != 0 or not output_path.is_file():
        log_parser_command(command, subprocess_response(completed), status="failed")
        return None

    log_parser_command(
        command,
        f"{subprocess_response(completed)}\n\nwrote {output_path.name}",
        status="succeeded",
    )
    return output_path


def split_audio_to_low_quality_mp3_chunks(
    source_path: Path,
    output_dir: Path,
    *,
    chunk_seconds: int = AUDIO_CHUNK_SECONDS,
) -> list[Path] | None:
    executable = ffmpeg_executable()
    if executable is None:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = output_dir / "chunk-%03d.mp3"
    command_parts = [
        executable,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "32k",
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        str(output_pattern),
    ]
    command = shlex.join(command_parts)
    log_parser_command(command, "started", status="running")
    try:
        completed = subprocess.run(
            command_parts,
            capture_output=True,
            check=False,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        log_parser_command(command, "command failed or timed out", status="failed")
        return None

    chunks = sorted(output_dir.glob("chunk-*.mp3"))
    if completed.returncode != 0 or not chunks:
        log_parser_command(command, subprocess_response(completed), status="failed")
        return None

    log_parser_command(
        command,
        f"{subprocess_response(completed)}\n\nwrote {len(chunks)} chunks",
        status="succeeded",
    )
    return chunks
