# Introduction

Mianotes is a local-first knowledge app that turns text, files, links, images, and audio into organised Markdown notes.

It is designed for small groups such as families, home labs, classrooms, and small teams. Everyone with access to the local instance can browse the shared knowledge base, while ownership still matters for editing, archiving, and accountability.

## Use Cases

- Save meeting notes, homework, receipts, trip plans, research, and reference documents.
- Upload files and keep their original source next to the generated Markdown note.
- Browse notes by person, topic, tag, or recency.
- Share a read-only note link with someone outside the household or team.
- Keep content transparent on disk instead of hiding it in a database blob.

## Storage Model

Mianotes stores note content as Markdown files:

```text
data/<username>/<topic>/<note_id>.md
```

SQLite stores the index and metadata: users, topics, tags, notes, comments, source files, sessions, and share tokens.

The filename is the note ID, not the note title. This keeps paths stable when titles change and makes future filesystem search simple to join back to note metadata.
