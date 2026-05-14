# Mianotes Web Service

Mianotes Web Service is the Python backend for Mianotes, an AI-powered local-first app that turns documents, images, links, audio, and text into organised Markdown notes.

The service stores note content on the filesystem, keeps lightweight indexes in SQLite, and exposes JSON REST APIs for the Mianotes web app and developer integrations.

## Current Status

This repository is in early implementation. See [PRD.md](PRD.md) for the current requirements and technical direction.

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
- Markdown notes under `/data/<username>/<topic>/<filename>.md`
- JSON sidecar files for note comments
- SQLite index for users, topics, notes, source files, and comments
- Repository layer designed for future PostgreSQL support
- OpenAI ChatGPT API for v1 note generation
- LiteParse for supported document and image parsing

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
mianotes-web-service --reload
```

The API health endpoint is available at:

```text
GET /api/health
```

FastAPI exposes interactive local API docs at:

```text
http://127.0.0.1:8000/docs
```

## Checks

```bash
python -m compileall src tests
pytest
ruff check .
```

## License

Mianotes Web Service is licensed under GPL-3.0. See [LICENCE](LICENCE).
