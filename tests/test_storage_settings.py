from pathlib import Path

from mianotes_web_service.services.storage_settings import (
    DEFAULT_DATABASE_FILE,
    StorageConfig,
    StorageLocation,
    add_storage_location,
    ensure_storage_location,
    read_storage_config,
    storage_database_path,
    write_storage_config,
)


def _storage_config(tmp_path: Path) -> StorageConfig:
    return StorageConfig(
        active_location="main",
        database_file=DEFAULT_DATABASE_FILE,
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
    assert storage_database_path(tmp_path / "research", next_config.database_file) == (
        tmp_path / "research" / ".mianotes" / "mia.db"
    )
    gitignore = (tmp_path / "research" / ".gitignore").read_text(encoding="utf-8")
    assert ".mianotes/" in gitignore
    assert ".mianotes/mia.db" in gitignore
    assert "mia.db" in gitignore
    assert "system.db" in gitignore
    assert "system.db-wal" in gitignore
    assert "system.db-shm" in gitignore
    assert "system.db-journal" in gitignore


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


def test_read_storage_config_migrates_legacy_database_file_name(tmp_path: Path):
    config_path = tmp_path / "storage.json"
    config_path.write_text(
        """
{
  "activeLocation": "default",
  "databaseFile": "mia.db",
  "allowedStorageLocations": [
    {
      "id": "default",
      "name": "Main workspace",
      "folderPath": "%s"
    }
  ]
}
""".strip()
        % str(tmp_path / "main"),
        encoding="utf-8",
    )

    config = read_storage_config(config_path, default_data_dir=tmp_path / "fallback")

    assert config.database_file == ".mianotes/mia.db"


def test_ensure_storage_location_moves_legacy_database_to_private_folder(tmp_path: Path):
    folder_path = tmp_path / "workspace"
    folder_path.mkdir()
    legacy_database = folder_path / "mia.db"
    legacy_database.write_text("legacy", encoding="utf-8")

    ensure_storage_location(folder_path)

    assert not legacy_database.exists()
    assert (folder_path / ".mianotes" / "mia.db").read_text(encoding="utf-8") == "legacy"
    assert ".mianotes/" in (folder_path / ".gitignore").read_text(encoding="utf-8")
