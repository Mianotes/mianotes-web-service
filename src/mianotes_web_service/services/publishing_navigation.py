from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from mianotes_web_service.db.models import Note
from mianotes_web_service.services.storage import short_id, slugify


def navigation_for_notes(notes: list[Note], *, include_folder: bool) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for note in notes:
        folder = note.folder
        groups.setdefault(folder.name, []).append(
            navigation_item_for_note(note, include_folder=include_folder)
        )
    return [{"title": title, "items": items} for title, items in groups.items()]


def navigation_with_new_notes(
    saved_navigation: list[dict[str, object]],
    notes: list[Note],
    *,
    include_folder: bool,
    since: datetime,
) -> list[dict[str, object]]:
    notes_by_path = {
        published_note_path(note, include_folder=include_folder): note
        for note in notes
    }
    navigation: list[dict[str, object]] = []
    groups_by_title: dict[str, dict[str, object]] = {}
    placed_paths: set[str] = set()

    for group in saved_navigation:
        title = group.get("title")
        items = group.get("items")
        if not isinstance(title, str) or not isinstance(items, list):
            continue
        next_items: list[dict[str, object]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not isinstance(path, str) or path in placed_paths:
                continue
            note = notes_by_path.get(path)
            if note is None:
                continue
            next_items.append(navigation_item_for_note(note, include_folder=include_folder))
            placed_paths.add(path)
        if next_items:
            next_group: dict[str, object] = {"title": title, "items": next_items}
            navigation.append(next_group)
            groups_by_title[title] = next_group

    for note in notes:
        path = published_note_path(note, include_folder=include_folder)
        if path in placed_paths or not note_changed_after(note, since):
            continue
        title = note.folder.name
        group = groups_by_title.get(title)
        if group is None:
            group = {"title": title, "items": []}
            groups_by_title[title] = group
            navigation.append(group)
        items = group["items"]
        if isinstance(items, list):
            items.append(navigation_item_for_note(note, include_folder=include_folder))
            placed_paths.add(path)

    return navigation


def navigation_item_for_note(note: Note, *, include_folder: bool) -> dict[str, object]:
    return {
        "title": note.title,
        "path": published_note_path(note, include_folder=include_folder),
    }


def updated_notes(
    notes: list[Note],
    *,
    include_folder: bool,
    previous_navigation_paths: set[str],
    since: datetime,
) -> list[dict[str, object]]:
    next_updated_notes: list[dict[str, object]] = []
    for note in notes:
        path = published_note_path(note, include_folder=include_folder)
        if path in previous_navigation_paths or not note_changed_after(note, since):
            continue
        next_updated_notes.append(
            {
                "title": note.title,
                "path": path,
            }
        )
    return next_updated_notes


def note_changed_after(note: Note, since: datetime) -> bool:
    changed_at = note.updated_at or note.created_at
    return as_utc(changed_at) > as_utc(since)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def navigation_paths(navigation: list[dict[str, object]]) -> set[str]:
    return set(navigation_paths_in_order(navigation))


def navigation_paths_in_order(navigation: list[dict[str, object]]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()

    def collect(items: Iterable[object]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if isinstance(path, str) and path and path not in seen:
                paths.append(path)
                seen.add(path)
            children = item.get("items")
            if isinstance(children, list):
                collect(children)

    collect(navigation)
    return paths


def published_note_path(note: Note, *, include_folder: bool) -> str:
    filename = f"{slugify(note.title)}-{short_id(note.id)}.html"
    if include_folder:
        return f"{note.folder.slug}/{filename}"
    return filename
