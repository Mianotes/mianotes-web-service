# Installation

Mianotes Web Service is a FastAPI application. It uses SQLite by default and stores generated note files under `data/`.

For contributor setup, see [Development](09-Development.md). For test commands, see [Testing](10-Testing.md).

## Step 1: Install dependencies

macOS:

```bash
brew install python ripgrep tesseract ffmpeg
```

Linux:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ripgrep tesseract-ocr ffmpeg
```

`ripgrep` is required for search. `tesseract` is used for local OCR on image
uploads. `ffmpeg` is optional unless you want to parse audio or video files.

On Apple Silicon Macs, make sure Tesseract is installed through the ARM
Homebrew path. If this command prints `Bad CPU type in executable`, the old
Intel binary is being used and image OCR will fail:

```bash
tesseract --version
```

Reinstall it with Homebrew, then restart the Mianotes service:

```bash
brew reinstall tesseract
```

## Step 2: Add environment variables

Create a `.env` file in the folder root.

For Ollama:

```env
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2:3b
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
MIANOTES_LLM_API_KEY=ollama
```

`llama3.2:3b` is a text model. Mianotes uses Tesseract first for local image
OCR, so text-heavy images can still be processed locally. If OCR is not enough,
Mianotes only uses cloud image OCR when OpenAI is configured.

For OpenAI:

```env
MIANOTES_LLM_PROVIDER=openai
MIANOTES_LLM_MODEL=gpt-4o-mini
MIANOTES_LLM_API_KEY=sk-...
```

With OpenAI, `gpt-4o-mini` can also be used as the image fallback. Mianotes
tries local Tesseract OCR first, then sends the image to OpenAI as a base64
image request when OCR is not enough.

If you want to use a different OpenAI model for image OCR, add:

```env
MIANOTES_LLM_IMAGE_MODEL=<multimodal-openai-model>
```

Do not add database or storage variables unless you want to change the default file locations. By default, Mianotes stores SQLite at `data/mia.db` and notes under `data/`.

### Agent and API client variables

The `.env` file above is read by the Mianotes web service. Other processes do
not automatically inherit it. If you want Codex, Claude, curl, scripts, or MCP
clients to call the API, also expose the API URL and an API token to the shell
where those tools run:

```bash
export MIANOTES_API_URL=http://127.0.0.1:8200
export MIANOTES_API_TOKEN=mia_your_token
```

For a permanent setup on macOS or Linux, add those two lines to your shell file:

```bash
~/.zshrc
```

or:

```bash
~/.bashrc
```

Then reload the shell:

```bash
source ~/.zshrc
```

For a one-off command from the web service folder, you can load the local
`.env` before calling the API:

```bash
set -a
. ./.env
set +a
curl -H "Authorization: Bearer ${MIANOTES_API_TOKEN}" \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/search?q=settings"
```

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

The first user joins through `POST /api/auth/join`. The service detects that no Mianotes instance has been configured, creates the first admin, stores the master password hash, and seeds the default `Mianotes` folder.

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

Image uploads use Tesseract first, so screenshots, scanned pages, receipts, and
other text-heavy images can be processed locally. `llama3.2:3b` cannot process
images. If Tesseract cannot extract useful text, configure OpenAI with a
multimodal model such as `gpt-4o-mini` for the image fallback.

`127.0.0.1` means the machine running the Python web service. If Mianotes and Ollama are both running on your Mac, this is the correct value.

If the backend runs on another box, such as Senseibox, then `127.0.0.1` points to that box instead of your Mac. In that case, use your Mac's LAN IP address:

```env
MIANOTES_LLM_BASE_URL=http://192.168.1.238:11434/v1
```

Ollama also needs to listen on the network for another machine to reach it.

## More setup options

If you are working on the Python backend, see [Development](09-Development.md).

If you want to run Mianotes as an always-on service, see [Customisation](05-Customisation.md).
