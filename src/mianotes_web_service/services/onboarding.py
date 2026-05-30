from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Folder, Note, SourceFile, User, new_id
from mianotes_web_service.services.storage import FilesystemStorage, short_id, summarize_text

ONBOARDING_FOLDER_NAME = "Mianotes"
ONBOARDING_FOLDER_SLUG = "mianotes"
ONBOARDING_NOTE_TITLE = "Getting Started"
ONBOARDING_ASSETS_DIR = Path(__file__).resolve().parents[1] / "onboarding_assets"
ONBOARDING_IMAGE_ALTS = {
    "onboarding_settings_workspace_switcher.jpg": "Settings workspace switcher",
    "onboarding_workspace_switcher.jpg": "Workspace switcher",
    "onboarding_mia.jpg": "Mia note tools",
    "onboarding_jobs.jpg": "Console job queue",
    "onboarding_screen_editor.jpg": "Markdown note editor",
    "onboarding_publish.jpg": "Publish notes screen",
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

{onboarding_settings_workspace_switcher}

The current workspace is always visible in the app, so you know where new notes, converted
files, folders, jobs, and published sites belong.

{onboarding_workspace_switcher}

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


def onboarding_note_text(*, folder_path: str, note_id: str) -> str:
    source_dir = f"sources/{short_id(note_id)}"
    encoded_folder_path = quote(folder_path.strip("/"), safe="/")

    def image_markdown(filename: str) -> str:
        asset_path = f"/markdown/{encoded_folder_path}/{source_dir}/{quote(filename)}"
        return f"![{ONBOARDING_IMAGE_ALTS[filename]}]({asset_path})"

    return ONBOARDING_NOTE_TEMPLATE.format(
        onboarding_settings_workspace_switcher=image_markdown(
            "onboarding_settings_workspace_switcher.jpg"
        ),
        onboarding_workspace_switcher=image_markdown("onboarding_workspace_switcher.jpg"),
        onboarding_mia=image_markdown("onboarding_mia.jpg"),
        onboarding_jobs=image_markdown("onboarding_jobs.jpg"),
        onboarding_screen_editor=image_markdown("onboarding_screen_editor.jpg"),
        onboarding_publish=image_markdown("onboarding_publish.jpg"),
    )


def copy_onboarding_assets(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for filename in ONBOARDING_IMAGE_ALTS:
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
    note_text = onboarding_note_text(folder_path=folder.path, note_id=note_id)
    paths = storage.write_text_note(
        username=user.username,
        folder=folder.path,
        title=ONBOARDING_NOTE_TITLE,
        text=note_text,
        filename=note_id,
    )
    if paths.source_path is not None:
        copy_onboarding_assets(paths.source_path.parent)
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
