from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, status

THEMES_DIR = Path(__file__).resolve().parents[1] / "publishing" / "themes"
GENERATOR_META_TAG = '<meta name="generator" content="Mianotes - https://github.com/Mianotes">'
DEFAULT_SITE_CONFIGURATION: dict[str, object] = {
    "brand": "mianotes",
    "version": "0.1.0",
    "headerLinks": [
        {"title": "GitHub", "url": "https://github.com/Mianotes"},
        {"title": "Contact", "url": "mailto:mianotes@proton.me"},
    ],
    "showPreviousVersions": True,
    "footerHtml": "Copyright © Your Name Here.",
}


@dataclass(frozen=True)
class PublishTheme:
    id: str
    name: str
    description: str
    version: str
    directory: Path


def list_publish_themes() -> list[PublishTheme]:
    themes: list[PublishTheme] = []
    if not THEMES_DIR.exists():
        return themes
    for directory in sorted(path for path in THEMES_DIR.iterdir() if path.is_dir()):
        metadata_path = directory / "theme.json"
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        themes.append(
            PublishTheme(
                id=str(metadata["id"]),
                name=str(metadata["name"]),
                description=str(metadata["description"]),
                version=str(metadata["version"]),
                directory=directory,
            )
        )
    theme_order = {"mialight": 0, "miadocs": 1, "miadev": 2, "miadark": 3}
    return sorted(themes, key=lambda theme: (theme_order.get(theme.id, 99), theme.name.lower()))


def read_publish_theme(theme_id: str) -> PublishTheme:
    theme = next((theme for theme in list_publish_themes() if theme.id == theme_id), None)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found")
    return theme


def default_site_configuration(theme: PublishTheme) -> dict[str, object]:
    configuration = json.loads(json.dumps(DEFAULT_SITE_CONFIGURATION))
    configuration["version"] = theme.version
    return configuration


def write_theme_assets(
    theme: PublishTheme,
    *,
    version_dir: Path,
    config: dict[str, object],
    navigation: list[dict[str, object]],
    search_index: list[dict[str, object]],
) -> None:
    from mianotes_web_service.services.publishing_static import json_for_script

    shutil.copy2(theme.directory / "styles.css", version_dir / "styles.css")
    site_runtime = (theme.directory / "site.js").read_text(encoding="utf-8")
    (version_dir / "site.js").write_text(
        (
            f"const SITE_CONFIGURATION = {json_for_script(config)};\n"
            f"const DOCS = {json_for_script({'groups': navigation})};\n"
            f"{site_runtime.rstrip()}\n"
        ),
        encoding="utf-8",
    )
    (version_dir / "search.js").write_text(
        f"const SEARCH_INDEX = {json_for_script(search_index)};\n",
        encoding="utf-8",
    )
    assets_dir = theme.directory / "assets"
    if assets_dir.exists():
        shutil.copytree(assets_dir, version_dir / "assets", dirs_exist_ok=True)
