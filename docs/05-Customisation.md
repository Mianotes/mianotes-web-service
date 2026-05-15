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

The parser stack is adapter-based. The registry currently implements plain text
and Markdown parsing directly, with command-backed adapters for:

- Poppler `pdftotext` for PDFs with selectable text.
- Pandoc for DOCX, HTML, Markdown, and related document conversion.
- Tesseract for image OCR.
- `mdformat` for Markdown cleanup.

Command-backed adapters report a clear unavailable error if the binary is not
installed. Hosted parsers can be added later behind the same parser adapter
boundary.

## Mia provider

Mia should start with OpenAI for v1. The agent layer should still be isolated
behind a service boundary so a future install can choose different providers or
local models for specific tasks.

## Agent access

Agent credentials should be scoped and revocable. They should not use the
browser household password or cookie session. Use `POST /api/tokens` from a
browser session to create a token, then send it as `Authorization: Bearer
mia_<token>` from agent clients.
