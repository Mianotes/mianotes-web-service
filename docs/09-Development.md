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
MIANOTES_LLM_PROVIDER=openai
MIANOTES_LLM_MODEL=gpt-4o-mini
MIANOTES_LLM_BASE_URL=
MIANOTES_LLM_API_KEY=
```

`MIANOTES_LLM_PROVIDER` supports:

- `openai` for OpenAI.
- `local` for an Ollama-style OpenAI-compatible server at
  `http://127.0.0.1:11434/v1`.
- `openai-compatible` for any custom OpenAI-compatible chat completion endpoint.

Mia also accepts `OPENAI_API_KEY`, `OPENAI_MODEL`, `OLLAMA_BASE_URL`,
`OLLAMA_MODEL`, and `OLLAMA_API_KEY` for compatibility with common tooling.
Legacy `MIANOTES_OPENAI_API_KEY` and `MIANOTES_OPENAI_MODEL` values are still
accepted for OpenAI installs. The provider-agnostic `MIANOTES_LLM_` variables
take precedence.

For local Ollama-style development:

```text
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2
```

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
seeds the default `Mianotes` project.

The frontend can call `POST /api/auth/check-email` first. If the response
contains `is_first_user: true`, it should explain that the first password
becomes the shared household password.
