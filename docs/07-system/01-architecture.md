# Architecture

Mianotes Web Service is a FastAPI application with filesystem-first note storage and a small relational index.

## Core principles

- The filesystem stores user-facing note content.
- Markdown is the durable note format.
- SQLite stores indexes, metadata, relationships, sessions, tokens, and jobs.
- API responses are JSON unless an endpoint explicitly returns a stored file.
- The backend owns permissions, parsing, job state, and persistence decisions.
- Browser users and AI agents use the same backend capability model.

## High-level components

```text
Human browser
    |
    v
Mianotes web app
    |
    v
FastAPI web service  <---- REST clients / agents
    |
    +--> SQLite metadata index
    |
    +--> Markdown note files and source files
    |
    +--> Parser adapter / MarkItDown / OCR
    |
    +--> Mia LLM provider boundary
    |
    +--> MCP stdio server calls the same REST API
```

## Storage layout

Generated notes and source files live under the configured data directory:

```text
data/<folder_slug>/<title_slug>-<note_id[:8]>.md
data/<folder_slug>/sources/<note_id[:8]>/original.<ext>
```

Folder rows store their filesystem path. Note rows store their Markdown filename. The full path is derived from those two values.

Later title edits do not rename files. This keeps URLs and filesystem references stable.

## Database responsibilities

SQLite tracks:

- users;
- folders;
- notes;
- source files;
- comments;
- tags;
- sessions;
- API tokens;
- share tokens;
- Mia jobs.

The repository and service boundaries keep storage concerns separate from the public API contract.

## Jobs

Long-running work is represented with durable rows in the `mia_jobs` table.

Status transitions:

```text
queued -> running -> succeeded
queued -> running -> failed
queued -> cancelled
```

This gives the web app and agent clients a stable polling model for file and URL ingestion.

## Search

Saved Markdown files are searched with `ripgrep`. The search service joins file matches back to note metadata before returning JSON results.

This keeps Markdown files as the source of note text while still giving API clients structured note IDs, titles, users, folders, tags, and timestamps.

## Authentication

The web app uses long-lived HTTP-only cookie sessions.

Agents and automation scripts use bearer tokens:

```http
Authorization: Bearer mia_<token>
```

Token hashes are stored in the database. Raw token values are returned only once when created.
