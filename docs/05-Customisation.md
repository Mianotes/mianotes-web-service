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
data/<username>/<topic>/<note_id>.md
data/<username>/<topic>/<note_id>.source.<ext>
```

Set `MIANOTES_DATA_DIR` to change the storage location.

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
pages, Mianotes first downloads the HTML using a browser-like user agent and
then passes the saved local HTML file to MarkItDown. This avoids sites that
block the default Python request user agent.

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

OpenAI compatibility variables are also supported: `OPENAI_API_KEY`,
`OPENAI_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and `OLLAMA_API_KEY`.

## Agent access

Agent credentials should be scoped and revocable. They should not use the
browser household password or cookie session. Use `POST /api/tokens` from a
browser session to create a token, then send it as `Authorization: Bearer
mia_<token>` from agent clients.

For MCP clients, set `MIANOTES_API_URL` and `MIANOTES_API_TOKEN`, then run
`python -m mianotes_web_service.mcp_server` or the installed `mianotes-mcp`
console script.
