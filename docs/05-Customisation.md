# Customisation

Mianotes is designed to be small, local, and adaptable.

## Ports

Mianotes services use the `8200` range:

```text
8200  web service
8201  alternate local service
8202  future service
```

## Storage

By default, generated notes and source files live under `data/`.

```text
data/<folder_slug>/<title_slug>-<note_id[:8]>.md
data/<folder_slug>/sources/<note_id[:8]>/original.<ext>
```

Folder directories are filesystem-safe slugs and are unique across the instance. Note filenames are readable enough for GitHub while still carrying a stable note ID prefix. Source files live under each folder's `sources/` directory, and Mianotes writes a folder-level `.gitignore` that ignores `/sources/` so generated Git backups can keep Markdown notes without committing original uploads.

Admins can switch between local Mianotes databases from the Settings screen.
The allowed database folders are stored in `storage.json` in the web service
root. Keep that file private to each installation.

Comments are stored in SQLite and do not use `.comments.json` sidecars.

## Database

SQLite is the default:

```text
MIANOTES_DATABASE_URL=
```

When `MIANOTES_DATABASE_URL` is empty, Mianotes stores SQLite at `data/mia.db`.
The app is structured so a future PostgreSQL adapter can be added without changing the API contract.

Database switching is documented in [Database](13-Database.md).

## Parser pipeline

The parser stack is adapter-based. The default adapter uses Microsoft
MarkItDown, which can convert common office documents, PDFs, images, audio,
HTML, text formats, archives, YouTube URLs, and more into Markdown-friendly
text.

For normal files, Mianotes passes the local source file to MarkItDown. For web
pages, Mianotes first downloads the HTML using a browser-like user agent, keeps
that raw source file, and uses `trafilatura` to extract the readable page
content before handing it to MarkItDown. This removes most navigation menus,
headers, footers, comments, and other page chrome while preserving useful links,
images, and tables. If extraction fails, Mianotes falls back to the saved HTML
file so URL ingestion still works.

Image files are different from PDFs and office documents. Mianotes first runs
MarkItDown's image converter so the source is handled by the same parser
adapter as other files. It then tries local Tesseract OCR for `.jpg`, `.jpeg`,
`.png`, `.tif`, and `.tiff` uploads. Tesseract works well for screenshots,
scanned pages, receipts, forms, and other text-heavy images.

Before using Tesseract, Mianotes checks that the binary can actually run. This
prevents old or incompatible binaries from silently breaking image ingestion.
For screenshots and other UI captures, Mianotes also runs a preprocessed OCR
pass that increases contrast and image size before choosing the best OCR result.

When OpenAI is configured with a multimodal model such as `gpt-4o-mini`,
MarkItDown sends the uploaded image as a base64 `image_url` request and asks
the model to transcribe and structure the image as Markdown. Mianotes only uses
this cloud image fallback when Tesseract cannot extract useful text. If OpenAI
is not configured, the note is published with a short Mia message explaining
that no text could be extracted and cloud image OCR can improve the result.

Install `ffmpeg` separately if you plan to parse audio or video sources. HTML,
document, and text conversion can ignore the `ffmpeg` warning. Specialist local
or hosted parsers can be added later behind the same parser adapter boundary.

## Mia provider

Mia uses an LLM provider boundary. OpenAI and local OpenAI-compatible servers
are supported out of the box.

```text
MIANOTES_LLM_PROVIDER=openai
MIANOTES_LLM_MODEL=gpt-4o-mini
MIANOTES_LLM_API_KEY=sk-...
# Optional, only needed if image OCR should use a different OpenAI model.
MIANOTES_LLM_IMAGE_MODEL=<multimodal-openai-model>
```

For local Ollama-style servers:

```text
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2:3b
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
MIANOTES_LLM_API_KEY=ollama
```

For other OpenAI-compatible servers:

```text
MIANOTES_LLM_PROVIDER=openai-compatible
MIANOTES_LLM_MODEL=<model-name>
MIANOTES_LLM_BASE_URL=<base-url>
MIANOTES_LLM_API_KEY=<token-or-local-placeholder>
```

## Agent access

Agent credentials should be scoped and revocable. They should not use the
browser master password or cookie session. Use `POST /api/tokens` from a
browser session to create a token, then send it as `Authorization: Bearer
mia_<token>` from agent clients.

For MCP clients, set `MIANOTES_API_URL` and `MIANOTES_API_TOKEN`, then run
`python -m mianotes_web_service.mcp_server` or the installed `mianotes-mcp`
console script.

Remember that the Mianotes service `.env` is local to the web service process.
External API clients and MCP clients need their own environment variables. For
regular use, add them to `~/.zshrc` or `~/.bashrc`.
