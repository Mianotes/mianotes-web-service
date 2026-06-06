from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from mianotes_web_service.services.env_file import read_env_value

PACKAGED_ENV_FILES = (
    Path("/Library/Application Support/Mianotes/env/mianotes.env"),
    Path("/etc/mianotes/mianotes.env"),
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    / "Mianotes"
    / "env"
    / "mianotes.env",
)

SHELL_ENV_REFERENCE_PATTERN = re.compile(
    r"^\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|"
    r"(?P<bare>[A-Za-z_][A-Za-z0-9_]*))$"
)


def source_env_file() -> Path | None:
    executable = os.environ.get("VIRTUAL_ENV") or sys.prefix
    if not executable:
        return None
    venv_path = Path(executable).expanduser().resolve()
    if venv_path.name != ".venv":
        return None
    return venv_path.parent / ".env"


def env_file_candidates(*, include_packaged: bool = False) -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("MIANOTES_ENV_FILE") or os.environ.get("MIANOTES_ENV_FILE_PATH")
    if configured:
        candidates.append(Path(configured).expanduser())

    source_env = source_env_file()
    if source_env:
        candidates.append(source_env)

    candidates.append(Path(".env"))
    if include_packaged:
        candidates.extend(PACKAGED_ENV_FILES)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        unique_candidates.append(resolved)
        seen.add(resolved)
    return unique_candidates


def read_env_file_value(key: str, *, include_packaged: bool = False) -> str | None:
    for candidate in env_file_candidates(include_packaged=include_packaged):
        value = read_env_value(candidate, key)
        if value:
            return value
    return None


def load_env_file_values(
    keys: Iterable[str],
    *,
    include_packaged: bool = False,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in keys:
        value = read_env_file_value(key, include_packaged=include_packaged)
        if value:
            values[key] = value
    return values


def env_reference_value(
    reference: object,
    *,
    include_packaged: bool = False,
) -> str | None:
    if not isinstance(reference, str) or not reference.startswith("env."):
        return None
    key = reference.removeprefix("env.").strip()
    if not key:
        return None
    return os.environ.get(key) or read_env_file_value(
        key,
        include_packaged=include_packaged,
    )


def shell_env_reference_value(
    value: str | None,
    *,
    include_packaged: bool = False,
) -> str | None:
    if not value:
        return value
    match = SHELL_ENV_REFERENCE_PATTERN.fullmatch(value.strip())
    if not match:
        return value
    key = match.group("braced") or match.group("bare")
    if not key:
        return None
    return os.environ.get(key) or read_env_file_value(
        key,
        include_packaged=include_packaged,
    )
