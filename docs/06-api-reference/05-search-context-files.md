# Search, context, sharing, and stored files API

This page covers endpoints that retrieve existing knowledge.

## Search notes

```text
GET /api/search
```

Authentication: session cookie or bearer token with `notes:read` or `admin`.

Query parameters:

| Parameter | Required | Description |
|---|---:|---|
| `q` | Yes | Search query. Minimum length is 1. |
| `limit` | No | Maximum matches. Defaults to `50`; maximum `100`. |

Example:

```text
GET /api/search?q=product%20launch&limit=10
```

Response shape:

```json
[
  {
    "note": {
      "id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
      "title": "Product launch meeting notes",
      "status": "ready"
    },
    "line_number": 12,
    "column": 8,
    "excerpt": "We discussed the product launch plan and next actions."
  }
]
```

Mianotes searches saved Markdown files with `ripgrep` and joins file matches back to note metadata.

## Get context

```text
GET /api/context
```

Authentication: session cookie or bearer token with `notes:read` or `admin`.

This endpoint retrieves full Markdown context from notes in a specific folder. It is designed for agents using shorthand such as:

```text
Mia(Mianotes > Settings Page)
```

Query parameters:

| Parameter | Required | Description |
|---|---:|---|
| `folder` | Yes | Folder name or slug. |
| `title` | Yes | Note title or context phrase. |
| `limit` | No | Maximum notes. Defaults to `5`; maximum `20`. |

The service first looks for matching note titles in the requested folder. If no title match is found, it searches Markdown files in that folder and returns matching notes.

## Share note

Create or replace a read-only share URL:

```text
POST /api/notes/{note_id}/share
```

Authentication: session cookie or bearer token with `share:write` or `admin`.

Response:

```json
{
  "share_url": "http://127.0.0.1:8200/api/notes/shared/NAC0tW5f..."
}
```

Disable sharing:

```text
DELETE /api/notes/{note_id}/share
```

## Get shared note

```text
GET /api/notes/shared/{token}
```

Authentication: none.

Returns a shared note without requiring a session or bearer token.

## Get shared source file

```text
GET /api/notes/shared/{token}/files/{source_file_id}
```

Authentication: none.

Returns a source file attached to a shared note.

## Get published static HTML

```text
GET /html
GET /html/{file_path}
```

Authentication: none.

Returns generated static HTML files from published sites. The `/html` root
redirects to the latest published version.

## Get published Markdown

```text
GET /markdown/{file_path}
```

Authenticated users and bearer-token clients with `notes:read` or `admin` can
read stored Markdown files under `data/markdown`.

Unauthenticated callers can only read Markdown or source files for notes marked
as published.

## Get stored folder file

```text
GET /{file_path}
```

Example:

```text
GET /mianotes/sources/4a95f146/original.pdf
```

Authentication: session cookie or bearer token with `notes:read` or `admin`.

Database files are never served. If a path escapes the data directory or points to private service data such as `mia.db`, the API returns `404`.
