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
data/<project_slug>/<title_slug>-<note_id[:8]>.md
data/<project_slug>/sources/<note_id[:8]>/original.<ext>
```

Project rows store their filesystem path, and note rows store their Markdown filename. The full path is derived from those two values. The filename combines a human-readable title slug with the first eight characters of the note ID. Later title edits do not rename files. Source files are grouped by note ID under the project's `sources/` directory, which is ignored by the project-level `.gitignore`.

Project slugs are unique across the instance because each project owns one
top-level storage directory.

## Database responsibilities

SQLite is the default database. The schema tracks:

- Users
- Projects
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
stores that raw HTML as the source file. The parser then asks `trafilatura` to
extract the main readable content before passing a cleaned HTML document to
MarkItDown. This avoids common bot-blocking behavior from sites that reject the
default Python request user agent, and it strips most navigation, header,
footer, sidebar, and comment content from generated Mianotes. If `trafilatura`
cannot extract enough content, Mianotes falls back to the raw saved HTML file.

`ffmpeg` is optional and only needed for audio or video sources.

## Jobs

Long-running work is represented with durable rows in the `mia_jobs` table.
Jobs move through clear status transitions:

```text
queued -> running -> succeeded
queued -> running -> failed
queued -> cancelled
```

This gives the web app and agent clients a stable polling model for file and
URL ingestion. Mia prompts sent through comments are synchronous and do not use
jobs.

## LLM providers

Mia calls language models through a provider boundary. The default provider is
OpenAI. Local mode uses the same OpenAI client against an OpenAI-compatible
endpoint, which makes local tools such as Ollama fit the same code path.

The supported provider values are:

- `openai`
- `local`
- `openai-compatible`

Job results record the provider and model used, so clients can explain whether a
note was improved by OpenAI or by a local model.

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
clients structured note IDs, titles, users, projects, tags, and timestamps.
