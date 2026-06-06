from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Folder, Note, SourceFile, User, new_id
from mianotes_web_service.services.note_tags import sync_note_tags
from mianotes_web_service.services.storage import FilesystemStorage, short_id, summarize_text
from mianotes_web_service.services.storage_settings import DEFAULT_LOCATION_ID
from mianotes_web_service.services.workspace_context import session_workspace

ONBOARDING_FOLDER_NAME = "Mianotes"
ONBOARDING_FOLDER_SLUG = "mianotes"
ONBOARDING_NOTE_TITLE = "Getting Started"
ONBOARDING_NOTE_TAGS = ["getting started", "welcome"]
ONBOARDING_ASSETS_DIR = Path(__file__).resolve().parents[1] / "onboarding_assets"
ONBOARDING_PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]+)\}")
ONBOARDING_IMAGE_ALTS = {
    "src/onboarding_assets/onboarding_workspace_switcher.png": "Workspace switcher",
}

ONBOARDING_NOTE_TEMPLATE = """# Welcome to Mianotes

Thank you for installing Mianotes.

As the admin, you are now setting up your secure local knowledge base. This is where your
notes, files, links, recordings, and AI agent outputs will live, fully under your control
and completely offline.

## Workspaces

A workspace is a local knowledge area. It maps to a normal folder on your machine, and
Mianotes stores that workspace's notes, sources, jobs, and index inside it.

Only admins can add workspaces. Go to Settings, add the folder you want Mianotes to use,
and Mianotes will prepare it as a local workspace.

The current workspace is always visible in the app, so you know where new notes, converted
files, folders, jobs, and published sites belong.

{src/onboarding_assets/onboarding_workspace_switcher.png}

## Getting started

A good first step is to create a folder for one real project. Once your folder is ready, try this:

1. Add a PDF, link, image, audio file, video, or plain note.
2. Open the Job Queue and watch Mia process it.
3. Read the generated Markdown note.
4. Edit the note and add tags.
5. Export it as a PDF, share it, or publish it when useful.

## What Mia does

Mia converts documents, links, images, audio, and text into Markdown notes you can read,
edit, search, and reuse.

When you connect an LLM, Mia can also answer questions about a note, summarise long
material, extract key points, improve rough text, and restructure content.

Mianotes works with local models like Llama, Qwen, Gemma, or DeepSeek. You can also connect
cloud providers such as OpenAI, Gemini, Claude, or any OpenAI-compatible API.

## Job Queue

File conversion requests are processed by Mia. Some jobs finish quickly. Others take longer,
especially long PDFs, audio, video, OCR-heavy images, or large batches of files.

Open the Job Queue to see what is queued, what is running, what completed, and what needs attention.

## Reading and editing notes

Once a note is ready, open it from the notes list. You can read the Markdown, edit it in the
rich text editor, ask Mia questions, add tags, move it to another folder, share it, export
it as a PDF, or publish it as part of a static site.

## Sharing and publishing

Mianotes can create share links for notes, export notes as PDFs, and publish selected notes
as a static HTML site.

If you configure a domain in Settings, share links will work for other people. If you do not
have a domain yet, you can still export a note as a PDF and share it yourself.

Publishing is useful when you want a clean documentation site, team handbook, project
archive, research hub, or public knowledge base generated from your notes.

## Tell us what to improve

Because Mianotes is in early development, your experience is incredibly important to us.
If you encounter bugs, missing features, or confusing workflows, please share your feedback
so we can improve: https://tally.so/r/xXvQbk

___
The Mianotes team
"""


def onboarding_note_text(
    *,
    note_id: str,
    workspace_id: str = DEFAULT_LOCATION_ID,
) -> str:
    encoded_workspace_id = quote(workspace_id, safe="")
    encoded_note_id = quote(note_id, safe="")

    def image_markdown(asset_reference: str) -> str:
        filename = onboarding_asset_filename(asset_reference)
        asset_path = (
            f"/api/workspaces/{encoded_workspace_id}/notes/{encoded_note_id}/images/"
            f"{quote(filename)}"
        )
        return f"![{ONBOARDING_IMAGE_ALTS[asset_reference]}]({asset_path})"

    def replace_placeholder(match: re.Match[str]) -> str:
        asset_reference = match.group(1)
        if asset_reference not in ONBOARDING_IMAGE_ALTS:
            raise KeyError(f"Unknown onboarding image placeholder: {asset_reference}")
        return image_markdown(asset_reference)

    return ONBOARDING_PLACEHOLDER_PATTERN.sub(
        replace_placeholder,
        ONBOARDING_NOTE_TEMPLATE,
    )


def onboarding_asset_filename(asset_reference: str) -> str:
    return Path(asset_reference).name


def copy_onboarding_assets(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for asset_reference in ONBOARDING_IMAGE_ALTS:
        filename = onboarding_asset_filename(asset_reference)
        source = ONBOARDING_ASSETS_DIR / filename
        if source.is_file():
            shutil.copy2(source, destination / filename)


def create_onboarding_note(session: Session, user: User, *, data_dir: Path) -> None:
    folder = session.scalars(
        select(Folder).where(Folder.slug == ONBOARDING_FOLDER_SLUG)
    ).one_or_none()
    if folder is None:
        folder = Folder(
            user_id=user.id,
            name=ONBOARDING_FOLDER_NAME,
            slug=ONBOARDING_FOLDER_SLUG,
            path=ONBOARDING_FOLDER_SLUG,
        )
        session.add(folder)
        session.flush()

    existing_note = session.scalars(
        select(Note).where(
            Note.folder_id == folder.id,
            Note.title == ONBOARDING_NOTE_TITLE,
        )
    ).one_or_none()
    if existing_note is not None:
        return

    storage = FilesystemStorage(data_dir)
    note_id = new_id()
    workspace = session_workspace(session)
    note_text = onboarding_note_text(
        note_id=note_id,
        workspace_id=workspace.id if workspace is not None else DEFAULT_LOCATION_ID,
    )
    paths = storage.write_text_note(
        username=user.username,
        folder=folder.path,
        title=ONBOARDING_NOTE_TITLE,
        text=note_text,
        filename=note_id,
    )
    copy_onboarding_assets(paths.directory / "images" / short_id(note_id))
    note = Note(
        id=note_id,
        user_id=user.id,
        folder_id=folder.id,
        title=ONBOARDING_NOTE_TITLE,
        filename=paths.note_path.name,
        note_path=str(paths.note_path),
        summary=summarize_text(note_text),
    )
    session.add(note)
    session.flush()
    sync_note_tags(session, note, ONBOARDING_NOTE_TAGS)

    if paths.source_path is not None:
        session.add(
            SourceFile(
                note_id=note.id,
                filename=str(paths.source_path.relative_to(paths.directory)),
                file_path=str(paths.source_path),
                original_filename="getting-started.txt",
                content_type="text/plain",
            )
        )
