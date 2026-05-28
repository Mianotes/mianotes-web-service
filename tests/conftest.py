from collections.abc import Generator
from pathlib import Path

import pytest

from mianotes_web_service.core.config import get_settings


@pytest.fixture(autouse=True)
def isolate_storage_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    monkeypatch.setenv("MIANOTES_STORAGE_CONFIG_PATH", str(tmp_path / "workspaces.json"))
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
