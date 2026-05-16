from pathlib import Path

from mianotes_web_service.services.storage import FilesystemStorage, make_username, slugify


def test_make_username_is_stable_and_hides_email():
    username = make_username("Person@example.com")

    assert username == make_username("person@example.com")
    assert "person" not in username
    assert len(username) == 16


def test_slugify_keeps_paths_safe():
    assert slugify("Project Notes!") == "project-notes"
    assert slugify("   ") == "untitled"


def test_note_paths_follow_storage_convention(tmp_path: Path):
    storage = FilesystemStorage(tmp_path)

    paths = storage.note_paths(
        username="abc123",
        project="Meeting Notes",
        filename="Kickoff Plan.pdf",
        source_extension=".pdf",
    )

    assert paths.directory == tmp_path / "abc123" / "meeting-notes"
    assert paths.note_path == tmp_path / "abc123" / "meeting-notes" / "kickoff-plan.md"
    assert paths.comments_path == (
        tmp_path / "abc123" / "meeting-notes" / "kickoff-plan.comments.json"
    )
    assert paths.source_path == tmp_path / "abc123" / "meeting-notes" / "kickoff-plan.pdf"
