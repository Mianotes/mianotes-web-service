# Installation

Mianotes Web Service is a FastAPI application. It uses SQLite by default and
stores generated note files under `data/`.

For contributor setup, see [Development](09-Development.md). For test commands,
see [Testing](10-Testing.md).

## Install

Install the system dependencies first.

macOS:

```bash
brew install python ripgrep ffmpeg
```

Linux:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ripgrep ffmpeg
```

`ripgrep` is required for search. `ffmpeg` is optional unless you want to parse
audio or video files.

## Start

For the simplest local run:

```bash
./start.sh
```

The script creates `.venv` if needed, installs Mianotes, installs the Codex and
Claude skills, initializes the database, and starts the API on port `8200`.

To use a different host or port:

```bash
MIANOTES_HOST=127.0.0.1 MIANOTES_PORT=8201 ./start.sh
```

## Manual install

Install from the repository with the installer:

```bash
./install.sh
```

The installer installs the Python package and copies the Mianotes skill to:

```text
~/.codex/skills/mianotes/SKILL.md
~/.claude/skills/mianotes/SKILL.md
```

For development dependencies:

```bash
./install.sh --dev
```

To refresh only the Codex and Claude skills:

```bash
./install.sh --skills-only
```

To install manually instead:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
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

`MIANOTES_LLM_PROVIDER` supports `openai`, `local`, and `openai-compatible`.
Use `local` for an Ollama-style OpenAI-compatible endpoint on your machine.

## Manual run commands

Manual run is the default path for local installs, quick testing, and people who
want to try Mianotes without installing a service.

```bash
mianotes-web-service init-db
mianotes-web-service --host 0.0.0.0 --port 8200
```

The default API URL is:

```text
http://127.0.0.1:8200
```

## systemd service

Use systemd for always-on local boxes such as Senseibox.

After installing a service file:

```bash
systemctl enable mianotes-web-service
systemctl start mianotes-web-service
```

The service should run:

```bash
mianotes-web-service --host 0.0.0.0 --port 8200
```

## First run

The first user joins through `POST /api/auth/join`. The service detects that no Mianotes instance has been configured, creates the first admin, stores the master password hash, and seeds the default `Mianotes` project.

The frontend can call `POST /api/auth/check-email` first. If the response contains `is_first_user: true`, it should explain that the first password becomes the master password for this instance.
