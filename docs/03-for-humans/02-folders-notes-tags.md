# Folders, notes, and tags

Folders, notes, and tags are the main organisation tools in Mianotes.

## Folders

Folders are group-visible. Any signed-in user can create a folder and add notes to any active folder.

Only the folder creator or an admin can archive a folder.

When a folder is archived, the folder directory is moved out of the active data area and into `data/.archived/`. The Markdown notes and source files are preserved.

## Notes

Notes store the knowledge people and agents reuse.

A note can be created from:

- plain text;
- Markdown;
- file upload;
- URL;
- image;
- audio or video when dependencies are installed.

The final note body is stored as a Markdown file on disk.

## Source files

When a note is created from a file or URL, Mianotes keeps the source next to the generated note.

Typical layout:

```text
data/<folder_slug>/<title_slug>-<note_id[:8]>.md
data/<folder_slug>/sources/<note_id[:8]>/original.<ext>
```

This makes the note readable while keeping source material available for review.

## Tags

Tags are global labels attached to notes.

Use tags when a note belongs to more than one mental category. For example, a note can live in the `Client Alpha` folder while also being tagged `invoice`, `urgent`, and `legal`.

Good tags are short, reusable, and boring:

```text
research
meeting
decision
todo
receipt
api
security
release
```

## Stars

Stars are private per user. Starring a note does not make it starred for everyone else.

Use stars for notes you personally need to revisit.

## Publishing and sharing

A note can be shared with a read-only link. Share links are note-level and revocable. A share link does not grant full workspace access.

For details, see [Sharing and comments](03-sharing-and-comments.md).
