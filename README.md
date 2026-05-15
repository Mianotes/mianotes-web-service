# Mianotes web service

Mianotes Web Service is the Python backend for Mianotes, a local-first knowledge
repository for humans and AI agents. It turns documents, images, links, audio,
and text into organised Markdown notes that can be improved by Mia and managed
programmatically through APIs and, later, MCP.

The service stores note content on the filesystem, keeps lightweight indexes in
SQLite, and exposes JSON REST APIs for the Mianotes web app, automation scripts,
and future agent integrations.

## Current status

This repository is in early implementation. See [PRD.md](PRD.md) and
[docs/](docs/README.md) for the current requirements and technical direction.

## Stack

- FastAPI for the HTTP API
- Pydantic for request and response validation
- SQLAlchemy for the database layer
- Alembic for migrations
- SQLite as the default local database
- pytest for tests
- Ruff for linting and formatting checks

Runtime dependencies intentionally avoid optional compiled server extras so the service is easier to install on small ARM Linux boxes.

## Architecture

- Filesystem-first note storage
- Markdown notes under `/data/<username>/<topic>/<note_id>.md`
- Database-backed note comments
- SQLite index for users, topics, notes, source files, comments, tokens, and jobs
- Repository layer designed for future PostgreSQL support
- OpenAI ChatGPT API for Mia-powered note generation and improvement
- Adapter-based local parser pipeline: plain text, Poppler `pdftotext`, Pandoc, Tesseract, and `mdformat`

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
mianotes-web-service init-db
mianotes-web-service --reload
```

The API health endpoint is available at:

```text
GET /api/health
```

The auth flow is household-based. The first user becomes the admin and sets the
shared master password. Later users join or log in with their email address and
the same master password. Sessions use long-lived HTTP-only cookies.

Agents and automation scripts authenticate with bearer tokens:

```text
Authorization: Bearer mia_<token>
```

Raw API token values are returned only once, when they are created.

The first APIs are:

```text
POST   /api/auth/check-email
POST   /api/auth/join
POST   /api/auth/login
GET    /api/auth/session
POST   /api/auth/logout

POST   /api/tokens             session or tokens:write token required
GET    /api/tokens             session or tokens:read token required
DELETE /api/tokens/{token_id}  session or tokens:write token required

GET    /api/jobs               session or notes:read token required
GET    /api/jobs/{job_id}      session or notes:read token required

POST   /api/users              admin session or admin token required
GET    /api/users              session or users:read token required
GET    /api/users/{user_id}    session or users:read token required
PATCH  /api/users/{user_id}    admin session or admin token required
DELETE /api/users/{user_id}    admin session or admin token required

POST   /api/topics             session or topics:write token required
GET    /api/topics             session or topics:read token required
GET    /api/topics/{topic_id}  session or topics:read token required
DELETE /api/topics/{topic_id}  session or topics:write token required

POST   /api/notes              session or notes:write token required
POST   /api/notes/from-text    session or notes:write token required
POST   /api/notes/from-file    session or notes:write token required
GET    /api/notes              session or notes:read token required
GET    /api/notes/{note_id}    session or notes:read token required
PATCH  /api/notes/{note_id}    session or notes:write token required
DELETE /api/notes/{note_id}    session or notes:write token required
POST   /api/notes/{note_id}/summarise  session or notes:write token required
POST   /api/notes/{note_id}/structure  session or notes:write token required
POST   /api/notes/{note_id}/extract    session or notes:write token required
POST   /api/notes/{note_id}/rewrite    session or notes:write token required
GET    /api/notes/{note_id}/comments  session or notes:read token required
POST   /api/notes/{note_id}/comments  session or comments:write token required
PUT    /api/notes/{note_id}/tags      session or tags:write token required
POST   /api/notes/{note_id}/share     session or share:write token required
GET    /api/notes/shared/{token}      guest read access

GET    /api/tags                 session or tags:read token required
GET    /api/search?q=term        session or notes:read token required
```

`PUT /api/notes/{note_id}/tags` replaces the note's full tag list. Notes can have up to 5 tags.
`GET /api/search` uses ripgrep to search saved Markdown files and returns note metadata with each match.

FastAPI exposes interactive local API docs at:

```text
http://127.0.0.1:8200/docs
```

Mianotes services use the `8200` range by convention. The web service defaults to
`8200`; use `8201`, `8202`, and so on for parallel local instances.

## Checks

```bash
python -m compileall src tests
pytest
ruff check .
```

## License

Mianotes Web Service is licensed under GPL-3.0. See [LICENCE](LICENCE).
