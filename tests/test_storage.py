from pathlib import Path

from mianotes_web_service.services.storage import (
    FilesystemStorage,
    make_username,
    note_stem,
    slugify,
)


def test_make_username_is_readable_stable_and_hides_email():
    username = make_username("Person@example.com", "Mia Agent")

    assert username == make_username("person@example.com", "Mia Agent")
    assert username.startswith("mia-agent-")
    assert "person" not in username
    assert "example" not in username


def test_slugify_keeps_paths_safe():
    assert slugify("Project Notes!") == "project-notes"
    assert slugify("   ") == "untitled"


def test_note_stem_uses_title_and_short_id():
    assert (
        note_stem("Planning Trip to Mallorca", "4a95f146-9d27-4c79-b7d8-34739aef8998")
        == "planning-trip-to-mallorca-4a95f146"
    )


def test_note_paths_follow_storage_convention(tmp_path: Path):
    storage = FilesystemStorage(tmp_path)

    paths = storage.note_paths(
        username="abc123",
        project="Meeting Notes",
        filename="4a95f146-9d27-4c79-b7d8-34739aef8998",
        title="Kickoff Plan",
        source_extension=".pdf",
    )

    assert paths.directory == tmp_path / "abc123" / "meeting-notes"
    assert paths.note_path == (
        tmp_path / "abc123" / "meeting-notes" / "kickoff-plan-4a95f146.md"
    )
    assert paths.comments_path == (
        tmp_path / "abc123" / "meeting-notes" / "kickoff-plan-4a95f146.comments.json"
    )
    assert paths.source_path == (
        tmp_path / "abc123" / "meeting-notes" / "kickoff-plan-4a95f146.pdf"
    )
