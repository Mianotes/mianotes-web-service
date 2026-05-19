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
data/<project_slug>/<title_slug>-<note_id[:8]>.md
data/<project_slug>/sources/<note_id[:8]>/original.<ext>
```

Project directories are filesystem-safe slugs and are unique across the instance. Note filenames are readable enough for GitHub while still carrying a stable note ID prefix. Source files live under each project's `sources/` directory, and Mianotes writes a project-level `.gitignore` that ignores `/sources/` so generated Git backups can keep Markdown notes without committing original uploads.

Set `MIANOTES_DATA_DIR` to change the storage location.

Comments are stored in SQLite and do not use `.comments.json` sidecars.

## Database

SQLite is the default:

```text
MIANOTES_DATABASE_URL=sqlite:///mianotes.db
```

The app is structured so a future PostgreSQL adapter can be added without changing the API contract.

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
```

For local Ollama-style servers:

```text
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
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
