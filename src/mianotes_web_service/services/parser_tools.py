from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mianotes_web_service.services.parser_runtime import (
    log_parser_command,
    subprocess_response,
)

FFMPEG_CANDIDATES = (
    "ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
)
AUDIO_TOOL_NAMES = ("ffmpeg", "ffprobe", "flac", "metaflac")
AUDIO_TOOL_DIR_CANDIDATES = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")
AUDIO_TOOL_VERSION_ARGS = {
    "ffmpeg": "-version",
    "ffprobe": "-version",
    "flac": "--version",
    "metaflac": "--version",
}
YOUTUBE_DOWNLOADER_CANDIDATES = ("yt-dlp", "youtube-dl")


def executable_version_works(path: str, *, version_arg: str = "-version") -> bool:
    command_parts = [path, version_arg]
    command = shlex.join(command_parts)
    try:
        completed = subprocess.run(
            command_parts,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
        log_parser_command(command, str(exc), status="failed")
        return False
    if completed.returncode == 0:
        first_line = (completed.stdout or "").splitlines()[0:1]
        log_parser_command(command, first_line[0] if first_line else "ok")
        return True
    log_parser_command(command, subprocess_response(completed), status="failed")
    return False


def working_audio_tool_dir() -> str | None:
    for candidate_dir in AUDIO_TOOL_DIR_CANDIDATES:
        tool_paths = [Path(candidate_dir) / tool for tool in AUDIO_TOOL_NAMES]
        if not all(path.exists() for path in tool_paths):
            continue
        if all(
            executable_version_works(
                str(path),
                version_arg=AUDIO_TOOL_VERSION_ARGS.get(path.name, "-version"),
            )
            for path in tool_paths
        ):
            return candidate_dir
    return None


@contextmanager
def prefer_working_audio_tools() -> Iterator[None]:
    original_path = os.environ.get("PATH", "")
    tool_dir = working_audio_tool_dir()
    if tool_dir is None:
        yield
        return

    path_parts = [part for part in original_path.split(os.pathsep) if part and part != tool_dir]
    os.environ["PATH"] = os.pathsep.join([tool_dir, *path_parts])
    log_parser_command("set audio tool PATH", os.environ["PATH"])
    try:
        yield
    finally:
        os.environ["PATH"] = original_path


def ffmpeg_executable() -> str | None:
    seen: set[str] = set()
    for candidate in FFMPEG_CANDIDATES:
        if "/" in candidate:
            path_candidate = candidate if Path(candidate).exists() else None
            log_parser_command(f"check executable {candidate}", path_candidate or "not found")
        else:
            path_candidate = shutil.which(candidate)
            log_parser_command(f"shutil.which('{candidate}')", path_candidate or "not found")
        if not path_candidate or path_candidate in seen:
            continue
        seen.add(path_candidate)
        if executable_version_works(path_candidate):
            return path_candidate
    return None


def youtube_downloader_executable() -> str | None:
    for candidate in YOUTUBE_DOWNLOADER_CANDIDATES:
        path_candidate = shutil.which(candidate)
        log_parser_command(f"shutil.which('{candidate}')", path_candidate or "not found")
        if path_candidate:
            return path_candidate

        venv_candidate = Path(sys.executable).with_name(candidate)
        if venv_candidate.exists():
            return str(venv_candidate)
    return None


def run_youtube_downloader(command_parts: list[str], *, timeout: int = 600) -> bool:
    command = shlex.join(command_parts)
    log_parser_command(command, "started", status="running")
    try:
        completed = subprocess.run(
            command_parts,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
        log_parser_command(command, str(exc), status="failed")
        return False

    if completed.returncode != 0:
        log_parser_command(command, subprocess_response(completed), status="failed")
        return False

    log_parser_command(command, subprocess_response(completed), status="succeeded")
    return True
