from collections.abc import Generator
from pathlib import Path

import pytest

from mianotes_web_service.core.config import get_settings


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    mark_expression = config.option.markexpr or ""
    if "performance" in mark_expression:
        return

    skip_performance = pytest.mark.skip(reason="run with pytest -m performance")
    for item in items:
        if "performance" in item.keywords:
            item.add_marker(skip_performance)


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
