# Ollama, OpenAI, and local models

Mia calls language models through a provider boundary. This lets one Mianotes instance use OpenAI, a local Ollama-style server, or another OpenAI-compatible endpoint without changing the REST API or MCP server.

## Local Ollama setup

Install Ollama, start it, then run a model.

### macOS with Homebrew

```bash
brew install ollama
ollama serve
```

In another terminal:

```bash
ollama run llama3.2:3b
```

Check that the model is installed:

```bash
ollama list
```

Use this `.env` configuration:

```env
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2:3b
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
MIANOTES_LLM_API_KEY=ollama
```

`127.0.0.1` means the machine running the Python web service. If Mianotes and Ollama are both running on your Mac, this is correct.

If the backend runs on another box, such as a home server or Senseibox, then `127.0.0.1` points to that box instead of your Mac. In that case, use the Mac's LAN IP address:

```env
MIANOTES_LLM_BASE_URL=http://192.168.1.238:11434/v1
```

Ollama must also be configured to listen on the network before another machine can reach it.

## OpenAI setup

```env
MIANOTES_LLM_PROVIDER=openai
MIANOTES_LLM_MODEL=gpt-4o-mini
MIANOTES_LLM_API_KEY=sk-...
```

With OpenAI configured, `gpt-4o-mini` can also be used as an image fallback when local OCR is not enough.

To use a different OpenAI model for image OCR:

```env
MIANOTES_LLM_IMAGE_MODEL=<multimodal-openai-model>
```

## OpenAI-compatible setup

Use this when you have another hosted or local endpoint that follows an OpenAI-compatible chat completions interface.

```env
MIANOTES_LLM_PROVIDER=openai-compatible
MIANOTES_LLM_MODEL=<model-name>
MIANOTES_LLM_BASE_URL=<base-url>
MIANOTES_LLM_API_KEY=<token-or-local-placeholder>
```

## Image uploads

Image files are handled in stages:

1. Mianotes runs MarkItDown's image converter.
2. Mianotes tries local Tesseract OCR for `.jpg`, `.jpeg`, `.png`, `.tif`, and `.tiff`.
3. For screenshots and UI captures, Mianotes also tries a preprocessed OCR pass with better contrast and size.
4. If local OCR cannot extract useful text and OpenAI is configured, Mianotes sends the image to a multimodal model as a cloud fallback.
5. If no fallback is configured, the note is saved with a short Mia message explaining that no text could be extracted.

Local text models such as `llama3.2:3b` cannot process images directly. Tesseract handles text-heavy images locally.

## Audio and video

Install `ffmpeg` if you plan to parse audio or video sources. HTML, document, and text conversion can ignore the `ffmpeg` warning.

Read next: [Parser and ingestion pipeline](../05-mia/03-parser-and-ingestion.md).
