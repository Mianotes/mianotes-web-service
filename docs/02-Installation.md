# Installation

Mianotes Web Service is a FastAPI application. It uses SQLite by default and stores generated note files under `data/`.

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
mianotes-web-service init-db
mianotes-web-service --reload
```

The default API URL is:

```text
http://127.0.0.1:8200
```

## Configuration

Environment variables use the `MIANOTES_` prefix:

```text
MIANOTES_HOST=0.0.0.0
MIANOTES_PORT=8200
MIANOTES_DATA_DIR=data
MIANOTES_DATABASE_URL=sqlite:///mianotes.db
MIANOTES_OPENAI_API_KEY=sk-...
MIANOTES_OPENAI_MODEL=gpt-4o-mini
```

Mia also accepts `OPENAI_API_KEY` and `OPENAI_MODEL` for compatibility with
standard OpenAI tooling. The `MIANOTES_` variables take precedence.

## First run

The first user joins through `POST /api/auth/join`. The service detects that no household exists, creates the first admin, stores the master password hash, and seeds the default `Mianotes` topic.

The frontend can call `POST /api/auth/check-email` first. If the response contains `is_first_user: true`, it should explain that the first password becomes the shared household password.
