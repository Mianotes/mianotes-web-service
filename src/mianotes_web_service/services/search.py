from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


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

    command = [
        rg_path,
        "--json",
        "--ignore-case",
        "--fixed-strings",
        "--glob",
        "*.md",
        "--",
        query,
        str(data_dir),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 1:
        return []
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ripgrep search failed")

    matches: list[RipgrepMatch] = []
    for line in completed.stdout.splitlines():
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
            break
    return matches
