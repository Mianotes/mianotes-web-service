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

Choose the run command based on what you are trying to do:

| Goal | Command | Use this when |
|---|---|---|
| Run Mianotes locally | `./start.sh` | You want to use Mianotes on your computer or local network. |
| Develop the backend | `./start-dev.sh` | You are changing Python code and want auto-reload. |
| Run manually | `mianotes-web-service init-db` then `mianotes-web-service --host 0.0.0.0 --port 8200` | You want full control over each step. |
| Run always-on | `systemctl start mianotes-web-service` | You installed Mianotes as a service on a local box or server. |

For the simplest local run, use `./start.sh`:

```bash
./start.sh
```

The script creates `.venv` if needed, installs Mianotes, installs the Codex and
Claude skills, initializes the database, and starts the API on port `8200`.

To use a different host or port:

```bash
MIANOTES_HOST=127.0.0.1 MIANOTES_PORT=8201 ./start.sh
```

During backend development, use `./start-dev.sh` instead:

```bash
./start-dev.sh
```

That script installs development dependencies and starts the API with reload
enabled.

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
MIANOTES_DATABASE_URL=
MIANOTES_LLM_PROVIDER=openai
MIANOTES_LLM_MODEL=gpt-4o-mini
MIANOTES_LLM_BASE_URL=
MIANOTES_LLM_API_KEY=
```

When `MIANOTES_DATABASE_URL` is empty, Mianotes stores SQLite at `data/mia.db`.

`MIANOTES_LLM_PROVIDER` supports `openai`, `local`, and `openai-compatible`.
Use `local` for an Ollama-style OpenAI-compatible endpoint on your machine.

## Local LLM with Ollama

Mianotes can use Ollama through its OpenAI-compatible API. For an 8GB M1
MacBook Air, `llama3.2:3b` is a good model to use.

On your Mac, install Ollama first, then run the model.

Option 1, easiest, using Homebrew:

```bash
brew install ollama
```

Start Ollama:

```bash
ollama serve
```

Open a second Terminal window and run:

```bash
ollama run llama3.2:3b
```

Option 2, download the Mac app:

```text
https://ollama.com/download/mac
```

Install it, open Ollama once, then run this in Terminal:

```bash
ollama run llama3.2:3b
```

To check it worked:

```bash
ollama list
```

Then add this to `.env`:

```env
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2:3b
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
MIANOTES_LLM_API_KEY=ollama
```

Restart the backend after changing `.env`:

```bash
mianotes-web-service --host 0.0.0.0 --port 8200
```

Or, if you use the script:

```bash
./start.sh
```

`127.0.0.1` means the machine running the Python web service. If Mianotes and
Ollama are both running on your Mac, this is the correct value.

If the backend runs on another box, such as Senseibox, then `127.0.0.1` points
to that box instead of your Mac. In that case, use your Mac's LAN IP address:

```env
MIANOTES_LLM_BASE_URL=http://192.168.1.238:11434/v1
```

Ollama also needs to listen on the network for another machine to reach it.

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
