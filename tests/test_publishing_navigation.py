from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mianotes_web_service.db.models import Folder, Note
from mianotes_web_service.services.publishing_navigation import (
    navigation_with_new_notes,
    published_note_path,
)


def _folder(name: str, slug: str, sort_order: int) -> Folder:
    return Folder(
        id=f"{slug}-folder",
        user_id="user-id",
        name=name,
        slug=slug,
        path=slug,
        sort_order=sort_order,
    )


def _note(
    note_id: str,
    title: str,
    folder: Folder,
    *,
    updated_at: datetime,
) -> Note:
    return Note(
        id=note_id,
        user_id="user-id",
        folder_id=folder.id,
        folder=folder,
        title=title,
        status="ready",
        note_path=f"/tmp/{folder.slug}/{note_id}.md",
        created_at=updated_at,
        updated_at=updated_at,
    )


def test_incremental_navigation_uses_current_folder_order_after_rename() -> None:
    since = datetime(2026, 6, 1, tzinfo=UTC)
    first_folder = _folder("About", "about", 10)
    renamed_folder = _folder("Workflow", "workflow", 20)
    last_folder = _folder("API", "api", 30)
    first_note = _note(
        "11111111-0000-0000-0000-000000000000",
        "About",
        first_folder,
        updated_at=since,
    )
    renamed_note = _note(
        "22222222-0000-0000-0000-000000000000",
        "Guide",
        renamed_folder,
        updated_at=since,
    )
    last_note = _note("33333333-0000-0000-0000-000000000000", "API", last_folder, updated_at=since)
    saved_navigation = [
        {
            "title": "About",
            "items": [
                {"title": "About", "path": published_note_path(first_note, include_folder=True)}
            ],
        },
        {
            "title": "For Humans",
            "items": [{"title": "Guide", "path": "for-humans/guide-22222222.html"}],
        },
        {
            "title": "API",
            "items": [
                {"title": "API", "path": published_note_path(last_note, include_folder=True)}
            ],
        },
    ]

    navigation = navigation_with_new_notes(
        saved_navigation,
        [first_note, renamed_note, last_note],
        include_folder=True,
        since=since + timedelta(days=1),
    )

    assert [group["title"] for group in navigation] == ["About", "Workflow", "API"]
    assert navigation[1]["items"] == [
        {"title": "Guide", "path": "workflow/guide-22222222.html"}
    ]


def test_incremental_navigation_preserves_saved_note_order_inside_current_folder() -> None:
    since = datetime(2026, 6, 1, tzinfo=UTC)
    folder = _folder("Docs", "docs", 10)
    alpha = _note("aaaaaaaa-0000-0000-0000-000000000000", "Alpha", folder, updated_at=since)
    beta = _note("bbbbbbbb-0000-0000-0000-000000000000", "Beta", folder, updated_at=since)
    saved_navigation = [
        {
            "title": "Docs",
            "items": [
                {"title": "Beta", "path": published_note_path(beta, include_folder=True)},
                {"title": "Alpha", "path": published_note_path(alpha, include_folder=True)},
            ],
        }
    ]

    navigation = navigation_with_new_notes(
        saved_navigation,
        [alpha, beta],
        include_folder=True,
        since=since + timedelta(days=1),
    )

    assert navigation == saved_navigation
