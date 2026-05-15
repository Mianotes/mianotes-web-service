# Mianotes Web Service

Mianotes Web Service is the Python backend for Mianotes, an AI-powered local-first app that turns documents, images, links, audio, and text into organised Markdown notes.

The service stores note content on the filesystem, keeps lightweight indexes in SQLite, and exposes JSON REST APIs for the Mianotes web app and developer integrations.

## Current Status

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
- SQLite index for users, topics, notes, source files, and comments
- Repository layer designed for future PostgreSQL support
- OpenAI ChatGPT API for v1 note generation
- Planned local parser pipeline: Poppler `pdftotext`, Pandoc, Tesseract, and `mdformat`

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

The first APIs are:

```text
POST   /api/auth/check-email
POST   /api/auth/join
POST   /api/auth/login
GET    /api/auth/session
POST   /api/auth/logout

POST   /api/users              admin session required
GET    /api/users              session required
GET    /api/users/{user_id}    session required
PATCH  /api/users/{user_id}    admin session required
DELETE /api/users/{user_id}    admin session required

POST   /api/topics
GET    /api/topics             session required
GET    /api/topics/{topic_id}  session required
DELETE /api/topics/{topic_id}  archives the topic

POST   /api/notes
POST   /api/notes/from-text
POST   /api/notes/from-file
GET    /api/notes              session required
GET    /api/notes/{note_id}    session required
PATCH  /api/notes/{note_id}
DELETE /api/notes/{note_id}
GET    /api/notes/{note_id}/comments  session required
POST   /api/notes/{note_id}/comments  session required
PUT    /api/notes/{note_id}/tags      session required
POST   /api/notes/{note_id}/share     owner/admin session required
GET    /api/notes/shared/{token}      guest read access

GET    /api/tags                 session required
```

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
