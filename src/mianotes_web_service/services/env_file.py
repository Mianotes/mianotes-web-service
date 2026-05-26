from __future__ import annotations

import os
import re
import stat
from pathlib import Path


def service_env_file_path() -> Path:
    configured = os.environ.get("MIANOTES_ENV_FILE") or os.environ.get("MIANOTES_ENV_FILE_PATH")
    return Path(configured or ".env").expanduser()


def _quote_env_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def upsert_env_value(path: Path, key: str, value: str) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=")
    next_line = f"{key}={_quote_env_value(value)}"
    updated = False
    next_lines: list[str] = []
    for line in lines:
        if pattern.match(line):
            if not updated:
                next_lines.append(next_line)
                updated = True
            continue
        next_lines.append(line)
    if not updated:
        next_lines.append(next_line)

    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    path.chmod(mode)
