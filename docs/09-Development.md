# Development

This page is for people working on the Python web service locally.

## Setup

Create a virtual environment and install the project with development
dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
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

## Manual run

Manual run is the default path for local development, quick testing, and trying
Mianotes without installing a service.

```bash
mianotes-web-service init-db
mianotes-web-service --host 0.0.0.0 --port 8200
```

For auto-reload during development:

```bash
mianotes-web-service --host 0.0.0.0 --port 8200 --reload
```

The default API URL is:

```text
http://127.0.0.1:8200
```

FastAPI exposes interactive local API docs at:

```text
http://127.0.0.1:8200/docs
```

## Service run

For always-on local boxes, use a systemd service. Manual run should stay the
default in the docs; systemd is the production-ish path for devices like
Senseibox.

The service should run the same command as the manual path:

```bash
mianotes-web-service --host 0.0.0.0 --port 8200
```

After installing a service file:

```bash
systemctl enable mianotes-web-service
systemctl start mianotes-web-service
```

## Ports

Mianotes services use the `8200` range:

```text
8200  web service
8201  alternate local service
8202  future service
```

## First run

The first user joins through `POST /api/auth/join`. The service detects that no
household exists, creates the first admin, stores the master password hash, and
seeds the default `Mianotes` topic.

The frontend can call `POST /api/auth/check-email` first. If the response
contains `is_first_user: true`, it should explain that the first password
becomes the shared household password.
