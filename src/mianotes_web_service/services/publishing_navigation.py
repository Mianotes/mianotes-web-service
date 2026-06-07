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
    previous_note_ranks = previous_navigation_note_ranks(
        saved_navigation,
        notes,
        include_folder=include_folder,
    )
    navigation: list[dict[str, object]] = []

    for title, group_notes in grouped_notes_by_current_folder(notes).items():
        ordered_notes: list[tuple[int, Note]] = []
        for current_index, note in enumerate(group_notes):
            if note.id not in previous_note_ranks and not note_changed_after(note, since):
                continue
            ordered_notes.append((current_index, note))
        if not ordered_notes:
            continue

        ordered_notes.sort(
            key=lambda item: (
                previous_note_ranks.get(item[1].id, len(notes) + item[0]),
                item[0],
            )
        )
        navigation.append(
            {
                "title": title,
                "items": [
                    navigation_item_for_note(note, include_folder=include_folder)
                    for _, note in ordered_notes
                ],
            }
        )

    return navigation


def grouped_notes_by_current_folder(notes: list[Note]) -> dict[str, list[Note]]:
    groups: dict[str, list[Note]] = {}
    for note in notes:
        groups.setdefault(note.folder.name, []).append(note)
    return groups


def previous_navigation_note_ranks(
    saved_navigation: list[dict[str, object]],
    notes: list[Note],
    *,
    include_folder: bool,
) -> dict[str, int]:
    notes_by_path = {
        published_note_path(note, include_folder=include_folder): note
        for note in notes
    }
    note_ids_by_short_id = unique_note_ids_by_short_id(notes)
    ranks: dict[str, int] = {}

    for rank, path in enumerate(navigation_paths_in_order(saved_navigation)):
        note = notes_by_path.get(path)
        note_id = (
            note.id if note is not None else note_ids_by_short_id.get(short_id_from_path(path))
        )
        if note_id is not None and note_id not in ranks:
            ranks[note_id] = rank

    return ranks


def unique_note_ids_by_short_id(notes: list[Note]) -> dict[str, str]:
    note_ids_by_short_id: dict[str, str] = {}
    duplicates: set[str] = set()
    for note in notes:
        value = short_id(note.id)
        if value in note_ids_by_short_id:
            duplicates.add(value)
        else:
            note_ids_by_short_id[value] = note.id
    for value in duplicates:
        note_ids_by_short_id.pop(value, None)
    return note_ids_by_short_id


def short_id_from_path(path: str) -> str | None:
    filename = path.rsplit("/", 1)[-1]
    if not filename.endswith(".html"):
        return None
    stem = filename[: -len(".html")]
    if "-" not in stem:
        return None
    return stem.rsplit("-", 1)[-1]


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
