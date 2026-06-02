from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from mianotes_web_service.core.config import get_settings


@dataclass(frozen=True)
class RipgrepMatch:
    path: Path
    line_number: int
    column: int
    excerpt: str


def search_markdown_files(data_dir: Path, query: str, *, limit: int = 50) -> list[RipgrepMatch]:
    rg_path = shutil.which("rg")
    if rg_path is None:
        raise RuntimeError("ripgrep is not installed")
    if not data_dir.exists():
        return []
    settings = get_settings()

    command = [
        rg_path,
        "--json",
        "--ignore-case",
        "--fixed-strings",
        "--max-count",
        str(limit),
        "--max-filesize",
        str(settings.search_max_file_bytes),
        "--glob",
        "*.md",
        "--",
        query,
        str(data_dir),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    matches: list[RipgrepMatch] = []
    start_time = time.monotonic()
    assert process.stdout is not None
    try:
        for line in process.stdout:
            if time.monotonic() - start_time > settings.search_timeout_seconds:
                process.kill()
                raise RuntimeError("ripgrep search timed out")
            event = json.loads(line)
            if event.get("type") != "match":
                continue
            data = event["data"]
            submatches = data.get("submatches") or [{"start": 0}]
            matches.append(
                RipgrepMatch(
                    path=Path(data["path"]["text"]).resolve(),
                    line_number=int(data["line_number"]),
                    column=int(submatches[0]["start"]) + 1,
                    excerpt=data["lines"]["text"].strip(),
                )
            )
            if len(matches) >= limit:
                process.terminate()
                break
        _, stderr = process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        _, stderr = process.communicate()
    if matches:
        return matches
    if process.returncode == 1:
        return []
    if process.returncode not in {0, None}:
        raise RuntimeError(stderr.strip() or "ripgrep search failed")
    return matches
