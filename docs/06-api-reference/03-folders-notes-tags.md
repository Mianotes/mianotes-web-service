# Folders, notes, and tags API

This page documents the core knowledge endpoints.

## Folder object

```json
{
  "id": "f054964b-419b-419a-87df-de668025b0e3",
  "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
  "name": "School",
  "slug": "school",
  "archived_at": null,
  "archived_by_user_id": null,
  "created_at": "2026-05-15T10:32:00Z",
  "updated_at": "2026-05-15T10:32:00Z"
}
```

## Create folder

```text
POST /api/folders
```

Authentication: session cookie or bearer token with `folders:write` or `admin`.

Request:

```json
{
  "name": "School",
  "is_pinned": false
}
```

The folder owner is always the current user.

## List folders

```text
GET /api/folders
```

Authentication: session cookie or bearer token with `folders:read` or `admin`.

Query parameters:

| Parameter | Description |
|---|---|
| `user_id` | Return folders created by a specific user. |
| `include_archived` | Include archived folders. Defaults to `false`. |

## Update folder

```text
PATCH /api/folders/{folder_id}
```

Authentication: session cookie or bearer token with `folders:write` or `admin`.

Admins can update any folder. Normal users can update only folders they created.

## Archive folder

```text
DELETE /api/folders/{folder_id}
```

Authentication: session cookie or bearer token with `folders:write` or `admin`.

Archived folders are hidden unless `include_archived=true`.

## Restore folder

```text
POST /api/folders/{folder_id}/restore
```

Authentication: session cookie or bearer token with `folders:write` or `admin`.

Admins can restore any archived folder. Normal users can restore only folders
they created.

Request:

```json
{
  "name": "Restored school notes",
  "is_pinned": true
}
```

Both fields are optional. If the original folder slug is already taken,
Mianotes creates a unique restored slug.

## Create note from text

```text
POST /api/notes/from-text
POST /api/notes
```

Authentication: session cookie or bearer token with `notes:write` or `admin`.

Request:

```json
{
  "folder_id": "f054964b-419b-419a-87df-de668025b0e3",
  "title": "Kickoff notes",
  "text": "We agreed to build Mianotes as a filesystem-first AI note app.",
  "tags": ["research", "planning"]
}
```

Tags are limited to 5 per note.

## Create note from file

```text
POST /api/notes/from-file
```

Authentication: session cookie or bearer token with `notes:write` or `admin`.

Request: `multipart/form-data`.

| Field | Required | Description |
|---|---:|---|
| `folder_id` | Yes | Folder ID for the note. |
| `file` | Yes | Source file to upload. |
| `title` | Yes | Note title. |

The response returns a pending note plus a queued `parse_file` job. Clients should poll `job_api_url`, then fetch `note_api_url` after success.

Supported upload extensions:

```text
.csv
.doc
.docx
.htm
.html
.jpeg
.jpg
.m4a
.md
.markdown
.mp3
.odt
.pdf
.png
.rtf
.tif
.tiff
.txt
.wav
```

## Create note from URL

```text
POST /api/notes/from-url
```

Authentication: session cookie or bearer token with `notes:write` or `admin`.

Request:

```json
{
  "folder_id": "f054964b-419b-419a-87df-de668025b0e3",
  "url": "https://example.com/articles/mianotes",
  "title": "Mianotes article",
  "tags": ["research", "links"]
}
```

The response returns a pending note plus a queued `parse_url` job.

## List notes

```text
GET /api/notes
```

Authentication: session cookie or bearer token with `notes:read` or `admin`.

Query parameters:

| Parameter | Description |
|---|---|
| `user_id` | Return notes created by a specific user. |
| `folder_id` | Return notes in a specific folder. |
| `starred` | Return notes starred or not starred by the authenticated user. |

List responses include metadata and a stored summary, but not full Markdown text.

## Get note

```text
GET /api/notes/{note_id}
```

Authentication: session cookie or bearer token with `notes:read` or `admin`.

Returns a full note including Markdown `text`, owner, folder, source files, tags, comment metadata, sharing metadata, and action hints.

## Update note

```text
PATCH /api/notes/{note_id}
```

Authentication: session cookie or bearer token with `notes:write` or `admin`.

Request fields:

```json
{
  "title": "Updated kickoff notes",
  "text": "Updated Markdown text.",
  "is_published": true,
  "tags": ["planning", "ai"]
}
```

Admins can update any note. Normal users can update only notes they created.

## Star note

```text
PATCH /api/notes/{note_id}/star
```

Stars are private per user.

Request:

```json
{
  "is_starred": true
}
```

## Delete note

```text
DELETE /api/notes/{note_id}
```

Deletes the note, stored Markdown file, source files, and related comments.

## Tags

List global tags:

```text
GET /api/tags
```

Replace a note's tag set:

```text
PUT /api/notes/{note_id}/tags
```

Request:

```json
{
  "tags": ["research", "planning"]
}
```
