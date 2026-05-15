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

Mia should start with OpenAI for v1. The agent layer should still be isolated
behind a service boundary so a future install can choose different providers or
local models for specific tasks.

Set `MIANOTES_OPENAI_API_KEY` or `OPENAI_API_KEY` to enable Mia jobs that call
OpenAI. `MIANOTES_OPENAI_MODEL` defaults to `gpt-4o-mini`; `OPENAI_MODEL` is
also supported for local developer convenience.

## Agent access

Agent credentials should be scoped and revocable. They should not use the
browser household password or cookie session. Use `POST /api/tokens` from a
browser session to create a token, then send it as `Authorization: Bearer
mia_<token>` from agent clients.

For MCP clients, set `MIANOTES_API_URL` and `MIANOTES_API_TOKEN`, then run
`python -m mianotes_web_service.mcp_server` or the installed `mianotes-mcp`
console script.
