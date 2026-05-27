from __future__ import annotations

import os
import re
import stat
from pathlib import Path

DEFAULT_SERVICE_API_URL = "http://127.0.0.1:8200"
LOCALHOST_SERVICE_API_URLS = {"http://localhost:8200"}


def service_env_file_path() -> Path:
    configured = os.environ.get("MIANOTES_ENV_FILE") or os.environ.get("MIANOTES_ENV_FILE_PATH")
    return Path(configured or ".env").expanduser()


def _quote_env_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unquote_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def read_env_value(path: Path, key: str) -> str | None:
    path = path.expanduser()
    if not path.exists():
        return None
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=\s*(.*)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return _unquote_env_value(match.group(1))
    return None


def ensure_service_api_url(path: Path) -> str:
    current_value = read_env_value(path, "MIANOTES_API_URL")
    if not current_value or current_value.rstrip("/") in LOCALHOST_SERVICE_API_URLS:
        upsert_env_value(path, "MIANOTES_API_URL", DEFAULT_SERVICE_API_URL)
        return DEFAULT_SERVICE_API_URL
    return current_value


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
