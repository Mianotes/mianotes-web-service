# Development

This page is for people working on the Python web service locally.

## Install system dependencies

macOS:

```bash
brew install python ripgrep ffmpeg
```

Linux:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ripgrep ffmpeg
```

Install `tesseract` too if you are working on image OCR.

## Start the development server

```bash
./start-dev.sh
```

The script:

- creates `.venv` if needed;
- installs Mianotes with development dependencies;
- installs the Codex and Claude skills;
- initializes the database;
- starts the API on port `8200` with reload enabled.

Use `./start-dev.sh` only when developing the backend. For normal local use, run `./start.sh`.

## Use a different host or port

```bash
MIANOTES_HOST=127.0.0.1 MIANOTES_PORT=8201 ./start-dev.sh
```

## Manual setup

```bash
python -m venv .venv
. .venv/bin/activate
./install.sh --dev
```

The installer copies the repository's Mianotes skill to:

```text
~/.codex/skills/mianotes/SKILL.md
~/.claude/skills/mianotes/SKILL.md
```

## Manual run

```bash
mianotes-web-service init-db
mianotes-web-service --host 0.0.0.0 --port 8200
```

For auto-reload:

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

For always-on local boxes, use a systemd service. Manual run should remain the default for docs and local development.

The service command should be:

```bash
mianotes-web-service --host 0.0.0.0 --port 8200
```

After installing a service file:

```bash
systemctl enable mianotes-web-service
systemctl start mianotes-web-service
```

## Development configuration

```env
MIANOTES_HOST=0.0.0.0
MIANOTES_PORT=8200
MIANOTES_DATA_DIR=data
MIANOTES_DATABASE_URL=
MIANOTES_LLM_PROVIDER=openai
MIANOTES_LLM_MODEL=gpt-4o-mini
MIANOTES_LLM_BASE_URL=
MIANOTES_LLM_API_KEY=
```

For local Ollama-style development:

```env
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2:3b
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
MIANOTES_LLM_API_KEY=ollama
```
