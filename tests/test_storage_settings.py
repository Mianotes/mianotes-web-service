from pathlib import Path

from mianotes_web_service.services.storage_settings import (
    StorageConfig,
    StorageLocation,
    add_storage_location,
    read_storage_config,
    workspace_database_path,
    write_storage_config,
)


def _storage_config(tmp_path: Path) -> StorageConfig:
    return StorageConfig(
        active_location="main",
        locations=[
            StorageLocation(id="main", name="Main workspace", folder_path=tmp_path / "main"),
            StorageLocation(id="archive", name="Archive", folder_path=tmp_path / "archive"),
        ],
    )


def test_add_storage_location_places_new_database_first(tmp_path: Path):
    config = _storage_config(tmp_path)

    next_config = add_storage_location(
        config,
        name="Research",
        folder_path=str(tmp_path / "research"),
    )

    assert [location.name for location in next_config.locations] == [
        "Research",
        "Main workspace",
        "Archive",
    ]
    assert next_config.active_location == "main"
    assert workspace_database_path(tmp_path / "data", next_config.locations[0].id) == (
        tmp_path / "data" / "workspaces" / "research.db"
    )
    assert not (tmp_path / "research" / ".mianotes").exists()
    assert not (tmp_path / "research" / ".gitignore").exists()


def test_storage_config_preserves_location_order(tmp_path: Path):
    config_path = tmp_path / "storage.json"
    config = add_storage_location(
        _storage_config(tmp_path),
        name="Research",
        folder_path=str(tmp_path / "research"),
    )

    write_storage_config(config_path, config)
    restored_config = read_storage_config(config_path, default_data_dir=tmp_path / "main")

    assert [location.name for location in restored_config.locations] == [
        "Research",
        "Main workspace",
        "Archive",
    ]
