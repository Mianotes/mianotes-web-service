# Publishing and settings API

This page covers static-site publishing and admin settings endpoints.

## List publish themes

```text
GET /api/publish/themes
```

Authentication: session cookie or bearer token with `notes:read` or `admin`.

Response:

```json
[
  {
    "id": "mialight",
    "name": "Mialight",
    "description": "Clean light documentation theme for Mianotes static sites.",
    "version": "0.1.0"
  },
  {
    "id": "miadocs",
    "name": "Miadocs",
    "description": "A polished article-reading theme for published notes and documentation.",
    "version": "0.1.0"
  },
  {
    "id": "miadark",
    "name": "Miadark",
    "description": "Dark documentation theme for Mianotes static sites.",
    "version": "0.1.0"
  }
]
```

## Get publish draft

```text
GET /api/publish/draft
```

Authentication: session cookie or bearer token with `notes:read` or `admin`.

Query parameters:

| Parameter | Description |
|---|---|
| `theme` | Theme ID. Defaults to `mialight`. |
| `folder_id` | Optional folder scope. Omit to publish all folders. |
| `tag_id` | Optional tag scope. |

`navigation` always contains every note that will appear in the static site.
`updated_notes` only lists notes whose generated paths were not present in the
previous publish navigation for the same scope.

## Publish site

```text
POST /api/publish
```

Authentication: session cookie or bearer token with `notes:write` or `admin`.

Request:

```json
{
  "folder_id": null,
  "tag_id": null,
  "theme": "mialight",
  "site_configuration": {
    "brand": "Federico",
    "version": "1.0.0",
    "headerLinks": [],
    "showPreviousVersions": true,
    "footerHtml": "Copyright (c) Federico Cargnelutti."
  },
  "navigation": [],
  "updated_notes": []
}
```

Response includes `site_url` and `download_url`.

## Download published site

```text
GET /api/publish/{site_id}/download
```

Authentication: session cookie or bearer token with `notes:read` or `admin`.

Returns a ZIP archive of the generated static site.

## Get storage settings

```text
GET /api/settings/storage
```

Authentication: admin session or bearer token with `admin`.

Returns the active storage location, database file name, database path, and
available storage locations with lightweight database stats. The web app labels
these storage locations as folders.

## Add storage location

```text
POST /api/settings/storage/locations
```

Authentication: admin session or bearer token with `admin`.

Request:

```json
{
  "name": "Work",
  "folder_path": "/Users/example/Mianotes/work"
}
```

Mianotes creates `.mianotes/mia.db` in that folder if needed and initialises the schema.

## Switch active storage location

```text
PATCH /api/settings/storage/active
```

Authentication: admin session or bearer token with `admin`.

Request:

```json
{
  "location_id": "work"
}
```

The response includes `session_ended: true`. The browser session is ended
because each folder has its own users and password state.

If Mia has queued or running jobs, the API returns `409` and asks the user to
try again after those jobs finish.

## Create service API key

```text
POST /api/settings/api-key
```

Authentication: admin session or bearer token with `admin`.

Creates a service-wide key used by local agents and MCP clients. The service
writes the raw key to its environment file and stores only a public verifier in
the active database. The raw key is returned only once:

```json
{
  "token": "mia_generated_key_returned_once"
}
```

See [API tokens](../04-for-agents/02-api-tokens.md) for setup, storage, and
client examples.
