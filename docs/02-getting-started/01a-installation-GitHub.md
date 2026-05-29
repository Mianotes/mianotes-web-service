# Installing from GitHub

Install from GitHub when you want editable source checkouts of Mianotes.

This path is best for developers, contributors, and people wiring Mianotes into local agent workflows.

## What gets installed

The GitHub installer creates two folders in the current directory:

```text
mianotes-web-service/
mianotes-dashboard/
```

It then runs each app's own development installer.

## Requirements

Install the system tools first.

### macOS

```bash
brew install python ripgrep tesseract ffmpeg
```

Install Node.js 20 or newer from nodejs.org or through your preferred package manager.

### Ubuntu and Debian

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ripgrep tesseract-ocr ffmpeg
```

Install Node.js 20 or newer before running the dashboard.

Tool purpose:

| Tool | Why Mianotes uses it |
|---|---|
| Python | Runs the FastAPI web service. |
| Node.js and npm | Build and run the React dashboard. |
| ripgrep | Searches saved Markdown notes. |
| Tesseract | Performs local OCR for image uploads. |
| ffmpeg | Enables audio and video parsing when needed. |

`ffmpeg` is optional unless you want to parse audio or video sources.

## Install

Run this from the folder where you want the source checkouts:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Mianotes/install/HEAD/install.sh)"
```

The installer downloads the web service and dashboard repositories, installs their dependencies, and leaves you with editable local projects.

## Install somewhere else

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Mianotes/install/HEAD/install.sh)" -- --dir ~/Mianotes
```

## Use a specific branch or tag

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Mianotes/install/HEAD/install.sh)" -- --ref main
```

## Create `.env`

The web service reads configuration from `mianotes-web-service/.env`.

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

Do not add database or workspace variables unless you want to change the default file locations. By default, Mianotes stores system state under `data/` and workspace content under each workspace's `.mianotes/` folder.

## Start Mianotes

```bash
cd mianotes-web-service
mianotes-web-service init-db
mianotes-web-service --host 0.0.0.0 --port 8200
```

The default local API URL is:

```text
http://127.0.0.1:8200
```

In another terminal, start the dashboard:

```bash
cd mianotes-dashboard
npm run dev
```

The dashboard URL is:

```text
http://127.0.0.1:8201
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

## Apple Silicon Tesseract check

On Apple Silicon Macs, make sure Tesseract is installed through the ARM Homebrew path.

```bash
tesseract --version
```

If the command prints `Bad CPU type in executable`, an old Intel binary is being used and image OCR will fail. Reinstall Tesseract, then restart the Mianotes service:

```bash
brew reinstall tesseract
```

## Next steps

1. Open the web app.
2. Create the first user.
3. Create or switch workspace.
4. Add a note from text, file, or URL.
5. Connect an agent with an API token when you are ready.

Read next: [First run](02-first-run.md) and [Configuration options](03-configuration.md).
