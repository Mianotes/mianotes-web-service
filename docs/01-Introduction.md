# Introduction

Mianotes is a local-first knowledge repository for humans and AI agents. It turns files, links, images, audio, and text into organised Markdown notes that agents can query, improve, and maintain through APIs and MCP, while humans collaborate through a web app.

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
