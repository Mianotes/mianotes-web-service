# API overview

The Mianotes web service exposes a local REST API. All endpoints return JSON unless the endpoint explicitly returns stored file bytes.

## Base URL

Local development and local deployments use port `8200` by default:

```text
http://127.0.0.1:8200
```

## Authentication

Protected endpoints accept one of:

- browser session cookie created by the auth flow;
- service-wide API key configured with `MIANOTES_API_KEY`;
- scoped per-user API token.

Bearer token shape:

```http
Authorization: Bearer mia_<token>
```

The service-wide bearer token acts as the first admin user in the current folder. Scoped bearer tokens must include the required scope or `admin`.

## Common errors

### Not authenticated

```json
{
  "detail": "Not signed in"
}
```

### Permission denied

```json
{
  "detail": "API token requires notes:read scope"
}
```

### Validation error

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "email"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

## Endpoint groups

| Area | Endpoints |
|---|---|
| Health and storage | `GET /api/health`, `GET /api/storage` |
| Auth | `POST /api/auth/check-email`, `POST /api/auth/join`, `POST /api/auth/login`, `GET /api/auth/session`, `POST /api/auth/logout` |
| Tokens | `POST /api/tokens`, `GET /api/tokens`, `DELETE /api/tokens/{token_id}`, `POST /api/settings/api-key` |
| Users | `POST /api/users`, `GET /api/users`, `GET /api/users/{user_id}`, `PATCH /api/users/{user_id}`, `POST /api/users/{user_id}/photo`, `DELETE /api/users/{user_id}` |
| Folders | `POST /api/folders`, `GET /api/folders`, `GET /api/folders/{folder_id}`, `PATCH /api/folders/{folder_id}`, `DELETE /api/folders/{folder_id}` |
| Notes | `POST /api/notes/from-text`, `POST /api/notes/from-file`, `POST /api/notes/from-url`, `GET /api/notes`, `GET /api/notes/{note_id}`, `PATCH /api/notes/{note_id}`, `PATCH /api/notes/{note_id}/star`, `DELETE /api/notes/{note_id}` |
| Sharing | `POST /api/notes/{note_id}/share`, `DELETE /api/notes/{note_id}/share`, `GET /api/notes/shared/{token}`, `GET /api/notes/shared/{token}/files/{source_file_id}` |
| Tags | `GET /api/tags`, `PUT /api/notes/{note_id}/tags` |
| Comments and Mia | `GET /api/notes/{note_id}/comments`, `POST /api/notes/{note_id}/comments`, `PATCH /api/notes/{note_id}/comments/{comment_id}`, `DELETE /api/notes/{note_id}/comments/{comment_id}` |
| Search and context | `GET /api/search`, `GET /api/context` |
| Jobs | `GET /api/jobs`, `GET /api/jobs/{job_id}` |
| Publishing | `GET /api/publish/themes`, `GET /api/publish/draft`, `POST /api/publish`, `GET /api/publish/{site_id}/download` |
| Settings | `GET /api/settings/storage`, `POST /api/settings/storage/locations`, `PATCH /api/settings/storage/active`, `POST /api/settings/api-key` |
| Stored files | `GET /{file_path}` |

## Health check

```text
GET /api/health
```

Authentication: none.

Example response:

```json
{
  "status": "ok",
  "service": "mianotes-web-service",
  "version": "0.1.0",
  "storage": {
    "data_dir": "data",
    "database_url": "sqlite:///data/.mianotes/mia.db"
  }
}
```

## Storage capacity

```text
GET /api/storage
```

Authentication: browser session or API token with `notes:read`.

Returns cached capacity information for the drive that stores Mianotes data. The service refreshes this snapshot at most once per hour.
