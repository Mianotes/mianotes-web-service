# Installation

Mianotes Web Service is a FastAPI application. It uses SQLite by default and stores generated note files under `data/`.

For contributor setup, see [Development](09-Development.md). For test commands, see [Testing](10-Testing.md).

## Step 1: Install dependencies

macOS:

```bash
brew install python ripgrep ffmpeg
```

Linux:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ripgrep ffmpeg
```

`ripgrep` is required for search. `ffmpeg` is optional unless you want to parse audio or video files.

## Step 2: Add environment variables

Create a `.env` file in the project root.

For Ollama:

```env
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2:3b
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
MIANOTES_LLM_API_KEY=ollama
```

For OpenAI:

```env
MIANOTES_LLM_PROVIDER=openai
MIANOTES_LLM_MODEL=gpt-4o-mini
MIANOTES_LLM_API_KEY=sk-...
```

Do not add database or storage variables unless you want to change the default file locations. By default, Mianotes stores SQLite at `data/mia.db` and notes under `data/`.

## Step 3: Start the server

```bash
./start.sh
```

This script automatically:

- creates `.venv` if needed
- installs Mianotes
- installs the Codex and Claude skills
- initialises the database
- starts the API on port `8200`

The default API URL is:

```text
http://127.0.0.1:8200
```

## First run

The first user joins through `POST /api/auth/join`. The service detects that no Mianotes instance has been configured, creates the first admin, stores the master password hash, and seeds the default `Mianotes` project.

The frontend can call `POST /api/auth/check-email` first. If the response contains `is_first_user: true`, it should explain that the first password becomes the master password for this instance.

## Ollama setup

If you want to use Ollama, install Ollama first, then run the model.

For an 8GB M1 MacBook Air, `llama3.2:3b` is a good model to use.

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

`127.0.0.1` means the machine running the Python web service. If Mianotes and Ollama are both running on your Mac, this is the correct value.

If the backend runs on another box, such as Senseibox, then `127.0.0.1` points to that box instead of your Mac. In that case, use your Mac's LAN IP address:

```env
MIANOTES_LLM_BASE_URL=http://192.168.1.238:11434/v1
```

Ollama also needs to listen on the network for another machine to reach it.

## More setup options

If you are working on the Python backend, see [Development](09-Development.md).

If you want to run Mianotes as an always-on service, see [Customisation](05-Customisation.md).
