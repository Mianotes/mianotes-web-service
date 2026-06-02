from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

DEFAULT_LOCATION_ID = "default"
WORKSPACE_DATABASE_DIR = "workspaces"
SYSTEM_DATABASE_FILENAME = "system.db"
SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


@dataclass(frozen=True)
class StorageLocation:
    id: str
    name: str
    folder_path: Path


@dataclass(frozen=True)
class StorageConfig:
    active_location: str
    locations: list[StorageLocation]

    @property
    def active_folder_path(self) -> Path:
        for location in self.locations:
            if location.id == self.active_location:
                return location.folder_path
        return self.locations[0].folder_path


def _location_id(name: str, folder_path: Path) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not base:
        base = re.sub(r"[^a-z0-9]+", "-", folder_path.name.lower()).strip("-")
    return base or DEFAULT_LOCATION_ID


def normalise_storage_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute():
        value = Path.cwd() / value
    return value.resolve()


def _normalise_workspace_id(value: str) -> str:
    workspace_id = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")
    return workspace_id or DEFAULT_LOCATION_ID


def workspace_database_path(data_dir: Path, workspace_id: str) -> Path:
    return normalise_storage_path(data_dir) / WORKSPACE_DATABASE_DIR / (
        f"{_normalise_workspace_id(workspace_id)}.db"
    )


def system_database_path(data_dir: Path) -> Path:
    return normalise_storage_path(data_dir) / SYSTEM_DATABASE_FILENAME


def _default_config(default_data_dir: Path) -> StorageConfig:
    folder_path = normalise_storage_path(default_data_dir)
    return StorageConfig(
        active_location=DEFAULT_LOCATION_ID,
        locations=[
            StorageLocation(
                id=DEFAULT_LOCATION_ID,
                name="Main workspace",
                folder_path=folder_path,
            )
        ],
    )


def read_storage_config(path: Path, *, default_data_dir: Path) -> StorageConfig:
    if not path.exists():
        config = _default_config(default_data_dir)
        write_storage_config(path, config)
        return config

    payload = json.loads(path.read_text(encoding="utf-8"))
    default_folder_path = payload.get("defaultFolderPath")
    raw_locations = payload.get("allowedStorageLocations") or []
    locations: list[StorageLocation] = []
    for item in raw_locations:
        if not item.get("folderPath"):
            continue
        folder_path = normalise_storage_path(item["folderPath"])
        name = str(item.get("name") or "Storage location")
        locations.append(
            StorageLocation(
                id=str(item.get("id") or _location_id(name, folder_path)),
                name=name,
                folder_path=folder_path,
            )
        )
    has_default_location = any(location.id == DEFAULT_LOCATION_ID for location in locations)
    if default_folder_path and not has_default_location:
        locations.insert(
            0,
            StorageLocation(
                id=DEFAULT_LOCATION_ID,
                name=str(payload.get("defaultName") or "Main workspace"),
                folder_path=normalise_storage_path(default_folder_path),
            ),
        )
    if not locations:
        return _default_config(default_data_dir)

    active_location = str(payload.get("activeLocation") or locations[0].id)
    if active_location not in {location.id for location in locations}:
        active_location = locations[0].id

    return StorageConfig(
        active_location=active_location,
        locations=locations,
    )


def write_storage_config(path: Path, config: StorageConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "activeLocation": config.active_location,
        "allowedStorageLocations": [
            {
                "id": location.id,
                "name": location.name,
                "folderPath": str(location.folder_path),
            }
            for location in config.locations
        ],
    }
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as temporary:
        json.dump(payload, temporary, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def ensure_storage_location(folder_path: Path) -> None:
    folder_path.mkdir(parents=True, exist_ok=True)
    if not folder_path.is_dir():
        raise ValueError("Storage location must be a folder.")
    probe = folder_path / ".mianotes-write-test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)


def add_storage_location(
    config: StorageConfig,
    *,
    name: str,
    folder_path: str,
) -> StorageConfig:
    normalised_path = normalise_storage_path(folder_path)
    ensure_storage_location(normalised_path)
    location_id = _location_id(name, normalised_path)
    existing_ids = {location.id for location in config.locations}
    if location_id in existing_ids:
        suffix = 2
        while f"{location_id}-{suffix}" in existing_ids:
            suffix += 1
        location_id = f"{location_id}-{suffix}"
    location = StorageLocation(id=location_id, name=name.strip(), folder_path=normalised_path)
    return StorageConfig(
        active_location=config.active_location,
        locations=[location, *config.locations],
    )


def remove_storage_location(config: StorageConfig, *, location_id: str) -> StorageConfig:
    if location_id == config.active_location:
        raise ValueError("The active storage location cannot be removed.")
    locations = [location for location in config.locations if location.id != location_id]
    if len(locations) == len(config.locations):
        raise LookupError("Storage location not found.")
    return StorageConfig(
        active_location=config.active_location,
        locations=locations,
    )


def activate_storage_location(config: StorageConfig, *, location_id: str) -> StorageConfig:
    location = next((item for item in config.locations if item.id == location_id), None)
    if location is None:
        raise LookupError("Storage location not found.")
    ensure_storage_location(location.folder_path)
    return StorageConfig(
        active_location=location.id,
        locations=config.locations,
    )
