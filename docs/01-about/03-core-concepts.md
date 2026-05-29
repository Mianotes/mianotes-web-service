# Core concepts

This page explains the words used throughout the documentation.

## Instance

A Mianotes workspace is a top-level knowledge area backed by a local folder. The private workspace SQLite database lives inside that folder at `.mianotes/mia.db`.

Small groups can share a Mianotes app by using the same master password. Everyone can read shared notes, browse by folder, browse by user, and add notes to active folders.

## User

A user is a human account in the current Mianotes folder. The first user becomes the admin for that folder.

Browser users authenticate with a session cookie. Agents should use API tokens instead of browser sessions.

## Folder

A folder is a shared workspace for related notes.

Folder rows are stored in SQLite, while each folder also owns a top-level filesystem directory under `data/`. A folder can be archived. When archived, the folder is hidden from normal lists and moved under `data/.archived/` so active folders stay clean.

## Note

A note is the main unit of knowledge.

The note body is a Markdown file on disk. Metadata lives in SQLite. A note can have source files, tags, comments, share links, and job history.

A note filename normally looks like:

```text
<title_slug>-<note_id>.md
```

Example:

```text
planning-trip-to-mallorca-4a95f146.md
```

## Source file

A source file is the original file or downloaded HTML used to create a note.

For file uploads, Mianotes stores the uploaded file under:

```text
data/<folder_slug>/sources/<note_id[:8]>/original.<ext>
```

Source files are kept next to the generated Markdown note but ignored by the folder-level `.gitignore` so Git backups can store notes without committing original uploads.

## Tag

Tags provide cross-folder grouping. Notes can be tagged with short labels such as `research`, `planning`, `client`, or `release`.

Tags are useful for both humans and agents because they make related notes easier to discover.

## Comment

A comment is a saved discussion item attached to a note.

Comments are useful for review, handoff, or reminders. If a comment body starts with `@mia`, Mianotes treats it as a private prompt to Mia instead of saving it as a shared comment.

## Job

A job represents background work, such as parsing an uploaded file or indexing a URL.

Jobs move through clear status transitions:

```text
queued -> running -> succeeded
queued -> running -> failed
queued -> cancelled
```

Clients should poll the job endpoint when a file or URL note is still being parsed.

## Mia

Mia is the built-in AI assistant. Mia works through backend service boundaries, not frontend-only behaviour. The backend owns permissions, persistence, parsing, and the LLM provider calls.

Read next: [Installation](../02-getting-started/01-Installation.md).
