from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import Folder, Note, SourceFile, User, new_id
from mianotes_web_service.services.storage import FilesystemStorage, summarize_text

ONBOARDING_FOLDER_NAME = "Mianotes"
ONBOARDING_FOLDER_SLUG = "mianotes"
ONBOARDING_NOTE_TITLE = "Getting Started"

ONBOARDING_NOTE_TEXT = """Thank you for installing Mianotes and giving it a place on your machine. That first login matters to us. You took the time to download, install, and trust a young open source app with your notes, files, and ideas. We built Mianotes for people who want useful local knowledge without sending everything to somebody else's cloud, and we are genuinely glad you are here.

Mianotes is still early, so we would love your help shaping it. If something breaks, feels confusing, or makes you think "this could be better", please tell us. You can open an issue on GitHub at https://github.com/Mianotes/mianotes-web-service/issues or email us at mianotes@proton.me. Bug reports, awkward moments, missing features, and thoughtful complaints all help make the app better.

## Workspaces

A workspace is a knowledge area. Each workspace maps to a normal folder on your computer, and Mianotes stores that workspace's database inside that folder. This keeps your content easy to understand: one workspace, one folder, one local knowledge base.

[image here]

Only admins can add a new workspace. Go to Settings, add the folder you want Mianotes to use, and Mianotes will create its local `.mianotes` data there. After that, everyone can switch between available workspaces using the workspace button in the top navigation.

[image here]

The current workspace is always visible in the app, so you know where new notes, converted files, folders, jobs, and published sites belong.

## The sidebar

The sidebar is your map of the current workspace.

[image here]

Use the plus button beside Folders to create folders for projects, subjects, clients, people, research, or anything else that helps you think. You can arrange folders by dragging and dropping them, so the important work stays close to the top.

[image here]

If you remove a folder by accident, Mianotes archives it instead of deleting your files. Admins and folder owners can restore archived folders, and files on disk are preserved. This is intentional: Mianotes should help organise your work, not make your data feel fragile.

## Add notes and convert files

The Add Note button is where most work starts.

[image here]

Every signed-in user can create a note, index a link, or convert files from their computer into Markdown. Mianotes can work with documents, PDFs, spreadsheets, images, audio, video, and links. The original source file is kept as a record, and the Markdown note becomes the clean version you can read, edit, search, ask Mia about, or publish.

[image here]

When you add a file or link, Mianotes creates a draft note first. You will be taken to the note page right away, but you can only edit the final Markdown once the job has completed. Until then, Mia is reading the source and preparing the note.

## Mia and the Console

File conversion requests are queued by Mia.

[image here]

Some jobs finish quickly. Others take longer, especially long PDFs, audio, video, OCR-heavy images, or large batches of files. The speed depends on your computer. A laptop with 16 GB RAM will not process large files the same way as a workstation with 64 GB RAM and a faster local model. That is normal.

The Console shows what Mia is doing.

[image here]

Use it to monitor the queue, see whether a job is running, completed, or failed, and inspect the technical details when something goes wrong. If you report an issue, the Console output is often the fastest way for us to understand what happened.

## Reading, editing, and asking Mia

Once a note is ready, open it from the listing page.

[image here]

You can edit the Markdown, ask Mia questions about the note, summarise it, extract key points, humanise text, add tags, move it to another folder, share it, export it as a PDF, or publish it as part of a static site.

[image here]

Profile and Users are intentionally simple. Your profile is where your personal details live. Users is where admins manage team members, update passwords, and decide who can administer the workspace.

[image here]

## Sharing and publishing

Mianotes can create share links for notes, export notes as PDFs, and publish a workspace or folder as a static HTML site.

[image here]

If you configure a domain in Settings, share links become reliable for other people. If you do not have a domain yet, you can still export a note as a PDF and share it yourself.

Publishing is useful when you want a clean documentation site, team handbook, project archive, research hub, or public knowledge base generated from your notes.

[image here]

## For technical admins

If you want Codex, Claude Code, Cursor, VS Code, scripts, or other local tools to use Mianotes, start by creating an API key in Settings.

[image here]

When an admin creates or rotates the API key, Mianotes adds the connection values to the service `.env` file automatically. That gives local agents and tools a stable place to discover the API URL and key.

The MCP server and the API key work across your Mianotes workspaces. When asking an agent to use Mianotes, include the workspace and folder you mean, for example:

```text
Before answering, get context from Mia(workspace: Mianotes, folder: Getting Started)
```

or:

```text
Save this summary in Mia(workspace: Mianotes, folder: Research)
```

## A good first five minutes

1. Create a folder for one real project.
2. Add a PDF, link, image, audio file, or video file.
3. Open Console and watch Mia process it.
4. Read the generated Markdown note.
5. Ask Mia to summarise it.
6. Edit the note and add tags.
7. Share or publish when it is useful.

Thank you again for trying Mianotes. We hope it feels local, practical, and calm. If it helps you turn scattered files and thoughts into something searchable and reusable, then it is doing exactly what it was made to do.
"""


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
    paths = storage.write_text_note(
        username=user.username,
        folder=folder.path,
        title=ONBOARDING_NOTE_TITLE,
        text=ONBOARDING_NOTE_TEXT,
        filename=note_id,
    )
    note = Note(
        id=note_id,
        user_id=user.id,
        folder_id=folder.id,
        title=ONBOARDING_NOTE_TITLE,
        filename=paths.note_path.name,
        note_path=str(paths.note_path),
        summary=summarize_text(ONBOARDING_NOTE_TEXT),
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
