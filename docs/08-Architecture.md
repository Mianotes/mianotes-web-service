# Architecture

Mianotes Web Service is a FastAPI application with filesystem-first note
storage and a small relational index.

## Core principles

- The filesystem stores user-facing note content.
- Markdown is the durable note format.
- SQLite stores indexes, metadata, relationships, sessions, tokens, and jobs.
- API responses are JSON unless the endpoint explicitly returns a stored file.
- The backend owns permissions, parsing, job state, and persistence decisions.
- Browser users and AI agents use the same backend capability model.

## Storage layout

Generated notes and source files live under the configured data directory:

```text
data/<username>/<topic>/<note_id>.md
data/<username>/<topic>/<note_id>.source.<ext>
```

The filename is the note ID, not the note title. This keeps paths stable when a
title changes and makes filesystem search results easy to join back to database
metadata.

## Database responsibilities

SQLite is the default database. The schema tracks:

- Users
- Topics
- Notes
- Source files
- Comments
- Tags
- Sessions
- API tokens
- Share tokens
- Mia jobs

The repository and service boundaries should stay clean enough to support a
future PostgreSQL adapter without changing the public API contract.

## Parsing

The parser layer is adapter-based. The default parser uses Microsoft MarkItDown
for documents, images, audio, HTML, text formats, archives, URLs, and related
source material.

For web pages, Mianotes first downloads HTML using a browser-like user agent and
then passes the local HTML file to MarkItDown. This avoids common bot-blocking
behavior from sites that reject the default Python request user agent.

`ffmpeg` is optional and only needed for audio or video sources.

## Jobs

Long-running work is represented with durable rows in the `mia_jobs` table.
Jobs move through clear status transitions:

```text
queued -> running -> succeeded
queued -> running -> failed
queued -> cancelled
```

This gives the web app and agent clients a stable polling model for parsing,
summarising, extracting, structuring, and rewriting work.

## Authentication

The web app uses long-lived HTTP-only cookie sessions. Agents and automation
scripts use scoped bearer tokens:

```text
Authorization: Bearer mia_<token>
```

Token hashes are stored in the database. Raw token values are returned only once
when the token is created.

## Search

Saved Markdown files are searched with ripgrep. The search service joins file
matches back to note metadata before returning JSON results.

This keeps the Markdown files as the source of note text while still giving API
clients structured note IDs, titles, users, topics, tags, and timestamps.
