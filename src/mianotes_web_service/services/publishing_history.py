from __future__ import annotations

import html
import re
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import PublishedSite
from mianotes_web_service.services.publishing_draft import load_json_list, load_json_object
from mianotes_web_service.services.publishing_static import json_for_script
from mianotes_web_service.services.publishing_theme import (
    DEFAULT_SITE_CONFIGURATION,
    GENERATOR_META_TAG,
)


def write_root_index(*, html_root: Path, version_slug: str) -> None:
    html_root.mkdir(parents=True, exist_ok=True)
    (html_root / "index.html").write_text(
        (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "  <head>\n"
            '    <meta charset="utf-8">\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"    {GENERATOR_META_TAG}\n"
            "    <title>mianotes documentation</title>\n"
            '    <script src="./navigation.js"></script>\n'
            "    <script>\n"
            "      const latestPath = `./${SITE_NAVIGATION.latest}/index.html`;\n"
            "      window.location.replace(latestPath);\n"
            "    </script>\n"
            "  </head>\n"
            f'  <body><a id="latest-link" href="./{html.escape(version_slug)}/index.html">'
            "Latest version</a><script>"
            "document.getElementById('latest-link').href = latestPath;"
            "</script>"
            "</body>\n"
            "</html>\n"
        ),
        encoding="utf-8",
    )


def write_navigation_js(
    *,
    session: Session,
    html_root: Path,
    current_site: PublishedSite,
) -> None:
    prune_missing_published_sites(session=session, html_root=html_root)
    entries = site_navigation_entries(
        session.scalars(select(PublishedSite).order_by(PublishedSite.created_at.desc())).all()
    )
    if not entries:
        entries = [
            {
                "label": f"{site_brand(current_site)} {current_site.version}",
                "path": f"{version_slug(current_site.version)}/index.html",
                "key": version_slug(current_site.version),
            }
        ]
    payload = {"latest": entries[0]["key"], "navigation": entries}
    (html_root / "navigation.js").write_text(
        f"const SITE_NAVIGATION = {json_for_script(payload)};\n",
        encoding="utf-8",
    )
    write_readme_md(html_root=html_root, current_site=current_site)


def write_readme_md(*, html_root: Path, current_site: PublishedSite) -> None:
    brand = markdown_text(site_brand(current_site))
    navigation = load_json_list(current_site.navigation, [])
    readme = [f"# {brand} Documentation", ""]
    if navigation:
        readme.extend(readme_navigation_lines(navigation, version_slug(current_site.version)))
    else:
        readme.append("_No notes were published._")
    readme.append("")
    (html_root / "README.md").write_text("\n".join(readme), encoding="utf-8")


def readme_navigation_lines(
    navigation: Iterable[dict[str, object]],
    current_version_slug: str,
) -> list[str]:
    lines: list[str] = []
    for group in navigation:
        title = group.get("title")
        items = group.get("items")
        if not isinstance(title, str) or not isinstance(items, list):
            continue
        lines.append(f"- **{markdown_text(title)}**")
        lines.extend(
            readme_item_lines(
                (item for item in items if isinstance(item, dict)),
                current_version_slug=current_version_slug,
                depth=1,
            )
        )
    return lines


def readme_item_lines(
    items: Iterable[dict[str, object]],
    *,
    current_version_slug: str,
    depth: int,
) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    child_indent_depth = depth + 1
    for item in items:
        title = item.get("title")
        path = item.get("path")
        children = item.get("items")
        if not isinstance(title, str):
            continue
        if isinstance(path, str) and path:
            lines.append(
                f"{indent}- [{markdown_text(title)}]({readme_link_path(current_version_slug, path)})"
            )
        else:
            lines.append(f"{indent}- **{markdown_text(title)}**")
        if isinstance(children, list):
            lines.extend(
                readme_item_lines(
                    (child for child in children if isinstance(child, dict)),
                    current_version_slug=current_version_slug,
                    depth=child_indent_depth,
                )
            )
    return lines


def prune_missing_published_sites(*, session: Session, html_root: Path) -> None:
    resolved_html_root = html_root.resolve()
    data_dir = resolved_html_root.parent
    did_prune = False
    for site in session.scalars(select(PublishedSite)).all():
        site_dir = (data_dir / site.html_path).resolve()
        if resolved_html_root not in site_dir.parents or not site_dir.is_dir():
            session.delete(site)
            did_prune = True
    if did_prune:
        session.commit()


def site_navigation_entries(sites: Iterable[PublishedSite]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for site in sites:
        next_version_slug = version_slug(site.version)
        if next_version_slug in seen:
            continue
        seen.add(next_version_slug)
        label = f"{site_brand(site)} {site.version}" if not entries else site.version
        entries.append(
            {
                "label": label,
                "path": f"{next_version_slug}/index.html",
                "key": next_version_slug,
            }
        )
    return entries


def site_brand(site: PublishedSite) -> str:
    configuration = load_json_object(site.site_configuration, DEFAULT_SITE_CONFIGURATION)
    return str(configuration.get("brand") or "mianotes")


def markdown_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("*", "\\*")
        .replace("_", "\\_")
    )


def readme_link_path(current_version_slug: str, item_path: str) -> str:
    clean_path = item_path.strip().lstrip("/")
    return f"{current_version_slug}/{clean_path}"


def version_slug(version: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", version.strip()).strip(".-_")
    return slug or "site"
