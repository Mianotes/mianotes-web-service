# Human workflow

Mianotes is built around shared knowledge with light ownership. Humans and AI agents can both create folders, add notes, improve notes, and leave comments.

## A normal human workflow

1. Create or join a Mianotes workspace.
2. Create a folder for a project, topic, class, client, trip, or research area.
3. Add a note from text, file, image, URL, or audio.
4. Let Mianotes convert the source into Markdown.
5. Review the note in the web app.
6. Add tags for discovery.
7. Ask Mia to summarise, extract, or restructure content when useful.
8. Share a read-only link when someone outside the workspace needs access.

## Shared workspaces

Teams, families, developers, researchers, and other small groups can use the same master password to join a Mianotes workspace.

Everyone can:

- read shared notes;
- browse by folder;
- browse by user;
- add notes to active folders;
- search saved Markdown.

Ownership still matters:

- the note creator can edit or delete their note;
- the folder creator can archive their folder;
- admins can manage any note or folder.

## Working with agents

Humans supervise the knowledge base. Agents help maintain it.

A useful pattern is:

1. A human creates the project folder.
2. An agent creates task notes as it works.
3. The agent tags the notes by topic or status.
4. The human reviews the notes, edits what matters, and shares the final result if needed.

## Good folder patterns

Use folders for high-level areas. Use tags for cross-cutting labels.

Examples:

| Folder | Good tags |
|---|---|
| `Mianotes` | `api`, `ui`, `security`, `release` |
| `Client Alpha` | `meeting`, `decision`, `todo`, `invoice` |
| `School` | `biology`, `revision`, `homework` |
| `Research` | `paper`, `summary`, `quote`, `follow-up` |
| `Agent worklog` | `codex`, `claude`, `bug`, `done` |

## Comments and Mia prompts

Normal comments are saved as discussion.

Mia prompts are private and start with `@mia`:

```text
@mia summarise this note for a busy project manager
```

Mia prompt responses are returned directly. They are not saved as comments and do not update the note unless you copy the result into the note.

Read next: [Folders, notes, and tags](02-folders-notes-tags.md).
