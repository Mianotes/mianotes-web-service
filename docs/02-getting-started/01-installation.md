# Installation

Mianotes Web Service is a FastAPI application. It uses SQLite by default and stores generated Markdown notes under `data/`.

## Requirements

Install the system tools first.

### macOS

```bash
brew install python ripgrep tesseract ffmpeg
```

### Linux

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ripgrep tesseract-ocr ffmpeg
```

Tool purpose:

| Tool | Why Mianotes uses it |
|---|---|
| Python | Runs the FastAPI web service. |
| ripgrep | Searches saved Markdown notes. |
| Tesseract | Performs local OCR for image uploads. |
| ffmpeg | Enables audio and video parsing when needed. |

`ffmpeg` is optional unless you want to parse audio or video sources.

## Apple Silicon Tesseract check

On Apple Silicon Macs, make sure Tesseract is installed through the ARM Homebrew path.

```bash
tesseract --version
```

If the command prints `Bad CPU type in executable`, an old Intel binary is being used and image OCR will fail. Reinstall Tesseract, then restart the Mianotes service:

```bash
brew reinstall tesseract
```

## Create `.env`

Create a `.env` file in the project root.

For a local Ollama-style model:

```env
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2:3b
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
MIANOTES_LLM_API_KEY=ollama
MIANOTES_API_KEY=replace-with-a-long-random-secret
```

For OpenAI:

```env
MIANOTES_LLM_PROVIDER=openai
MIANOTES_LLM_MODEL=gpt-4o-mini
MIANOTES_LLM_API_KEY=sk-...
MIANOTES_API_KEY=replace-with-a-long-random-secret
```

Do not add database or storage variables unless you want to change the default file locations. By default, Mianotes stores SQLite at `data/.mianotes/mia.db` and notes under `data/`.

## Start the server

```bash
./start.sh
```

The script automatically:

- creates `.venv` if needed;
- installs Mianotes;
- installs the Codex and Claude skills;
- initialises the database;
- starts the API on port `8200`.

The default local URL is:

```text
http://127.0.0.1:8200
```

## Check that it is running

```bash
curl -sS http://127.0.0.1:8200/api/health
```

Expected shape:

```json
{
  "status": "ok",
  "service": "mianotes-web-service",
  "version": "0.1.0"
}
```

## Next steps

1. Open `http://127.0.0.1:8200`.
2. Create the first user.
3. Create a folder.
4. Add a note from text, file, or URL.
5. Connect an agent with an API token when you are ready.

Read next: [First run](02-first-run.md) and [Configuration options](03-configuration.md).
