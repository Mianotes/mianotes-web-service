# APIs

This document describes the current Mianotes web service API.

All endpoints return JSON unless the endpoint explicitly returns a stored file.
Protected endpoints accept either the browser session cookie created by the auth
flow or an agent API token sent as a bearer token.

```text
Authorization: Bearer mia_<token>
```

Browser sessions represent an interactive household user and bypass token scope
checks. Bearer tokens must include the required scope, or the `admin` scope.

## Base URL

Local development and local deployments use port `8200` by default.

```text
http://127.0.0.1:8200
```

## Common errors

The API currently uses FastAPI error responses.

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

## Common objects

### User

```json
{
  "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
  "email": "matt@example.com",
  "name": "Matt",
  "username": "u_2d9f6b1a",
  "is_admin": true,
  "created_at": "2026-05-15T10:30:00Z",
  "updated_at": "2026-05-15T10:30:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique user ID. |
| `email` | string | User email address. Email is unique. |
| `name` | string | User display name. |
| `username` | string | App-generated filesystem-safe username. |
| `is_admin` | boolean | Whether the user is an admin. |
| `created_at` | string | ISO 8601 creation timestamp. |
| `updated_at` | string | ISO 8601 update timestamp. |

### Topic

```json
{
  "id": "f054964b-419b-419a-87df-de668025b0e3",
  "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
  "name": "Holidays Mallorca",
  "slug": "holidays-mallorca",
  "archived_at": null,
  "archived_by_user_id": null,
  "created_at": "2026-05-15T10:32:00Z",
  "updated_at": "2026-05-15T10:32:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique topic ID. |
| `user_id` | string | ID of the user who created the topic. |
| `name` | string | Topic display name. |
| `slug` | string | Filesystem-safe topic slug. |
| `archived_at` | string \| null | ISO 8601 timestamp when the topic was archived. |
| `archived_by_user_id` | string \| null | ID of the user who archived the topic. |
| `created_at` | string | ISO 8601 creation timestamp. |
| `updated_at` | string | ISO 8601 update timestamp. |

### Note list item

```json
{
  "id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
  "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
  "topic_id": "f054964b-419b-419a-87df-de668025b0e3",
  "title": "Kickoff notes",
  "status": "ready",
  "source_type": "text",
  "revision_number": 1,
  "is_published": false,
  "note_path": "/home/arduino/mianotes-web-service/data/u_2d9f6b1a/holidays-mallorca/4a95f146-9d27-4c79-b7d8-34739aef8998.md",
  "created_at": "2026-05-15T10:35:00Z",
  "updated_at": "2026-05-15T10:35:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique note ID. |
| `user_id` | string | ID of the user who created the note. |
| `topic_id` | string | ID of the topic containing the note. |
| `title` | string | Note title. |
| `status` | string | Note status. Current values include `ready` and `pending_parse`. |
| `source_type` | string | Source type such as `text`, `pdf`, `image`, `document`, or `file`. |
| `revision_number` | number | Revision counter incremented when note text or title changes. |
| `is_published` | boolean | Whether the note is marked as published. |
| `note_path` | string | Absolute filesystem path to the Markdown note. |
| `created_at` | string | ISO 8601 creation timestamp. |
| `updated_at` | string | ISO 8601 update timestamp. |

### Note

Full note responses include the note content, owner, topic, source files, tags,
comments metadata, sharing metadata, and API action hints.

```json
{
  "id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
  "user": {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "u_2d9f6b1a",
    "is_admin": true,
    "created_at": "2026-05-15T10:30:00Z",
    "updated_at": "2026-05-15T10:30:00Z"
  },
  "topic": {
    "id": "f054964b-419b-419a-87df-de668025b0e3",
    "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "name": "Holidays Mallorca",
    "slug": "holidays-mallorca",
    "archived_at": null,
    "archived_by_user_id": null,
    "created_at": "2026-05-15T10:32:00Z",
    "updated_at": "2026-05-15T10:32:00Z"
  },
  "created_at": "2026-05-15T10:35:00Z",
  "updated_at": "2026-05-15T10:35:00Z",
  "title": "Kickoff notes",
  "status": "ready",
  "source_type": "text",
  "revision_number": 1,
  "is_published": false,
  "published_at": null,
  "shared_at": null,
  "text": "# Kickoff notes\n\nWe agreed to build Mianotes...",
  "note_url": "http://127.0.0.1:8200/data/u_2d9f6b1a/holidays-mallorca/4a95f146-9d27-4c79-b7d8-34739aef8998.md",
  "source_files": [
    {
      "id": "b5e20df8-bd95-45f0-a4f6-a2ee2db3f7b6",
      "original_filename": "kickoff.source.txt",
      "content_type": "text/plain",
      "url": "http://127.0.0.1:8200/data/u_2d9f6b1a/holidays-mallorca/4a95f146-9d27-4c79-b7d8-34739aef8998.source.txt"
    }
  ],
  "comments_count": 0,
  "comments_url": "http://127.0.0.1:8200/api/notes/4a95f146-9d27-4c79-b7d8-34739aef8998/comments",
  "tags": [
    {
      "id": "d4fb05d7-3c77-4800-b3f9-1708ed8b7307",
      "name": "Research",
      "slug": "research",
      "created_at": "2026-05-15T10:35:00Z",
      "updated_at": "2026-05-15T10:35:00Z"
    }
  ],
  "share_url": null,
  "actions": {
    "self": {
      "method": "GET",
      "url": "http://127.0.0.1:8200/api/notes/4a95f146-9d27-4c79-b7d8-34739aef8998"
    },
    "update": {
      "method": "PATCH",
      "url": "http://127.0.0.1:8200/api/notes/4a95f146-9d27-4c79-b7d8-34739aef8998"
    },
    "delete": {
      "method": "DELETE",
      "url": "http://127.0.0.1:8200/api/notes/4a95f146-9d27-4c79-b7d8-34739aef8998"
    },
    "comments": {
      "method": "GET",
      "url": "http://127.0.0.1:8200/api/notes/4a95f146-9d27-4c79-b7d8-34739aef8998/comments"
    }
  }
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique note ID. |
| `user` | object | User who created the note. |
| `topic` | object | Topic containing the note. |
| `created_at` | string | ISO 8601 creation timestamp. |
| `updated_at` | string | ISO 8601 update timestamp. |
| `title` | string | Note title. |
| `status` | string | Note status. |
| `source_type` | string | Source type. |
| `revision_number` | number | Revision counter. |
| `is_published` | boolean | Whether the note is marked as published. |
| `published_at` | string \| null | ISO 8601 publish timestamp. |
| `shared_at` | string \| null | ISO 8601 share timestamp. |
| `text` | string | Markdown note text. |
| `note_url` | string | URL for the Markdown file. |
| `source_files` | object[] | Source files associated with the note. |
| `comments_count` | number | Number of comments with body text. |
| `comments_url` | string | URL for note comments. |
| `tags` | object[] | Tags attached to the note. |
| `share_url` | string \| null | Public read-only share URL, when sharing is enabled. |
| `actions` | object | API method and URL hints for common note actions. |

### Tag

```json
{
  "id": "d4fb05d7-3c77-4800-b3f9-1708ed8b7307",
  "name": "Research",
  "slug": "research",
  "created_at": "2026-05-15T10:35:00Z",
  "updated_at": "2026-05-15T10:35:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique tag ID. |
| `name` | string | Tag display name. |
| `slug` | string | Normalized tag slug. |
| `created_at` | string | ISO 8601 creation timestamp. |
| `updated_at` | string | ISO 8601 update timestamp. |

### Comment

```json
{
  "id": "0ebd5d0d-b40c-4084-aeb4-cf687ab81922",
  "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
  "user": {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "u_2d9f6b1a",
    "is_admin": true,
    "created_at": "2026-05-15T10:30:00Z",
    "updated_at": "2026-05-15T10:30:00Z"
  },
  "body": "This is useful for the next call.",
  "created_at": "2026-05-15T10:40:00Z",
  "updated_at": "2026-05-15T10:40:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique comment ID. |
| `note_id` | string | ID of the note the comment belongs to. |
| `user` | object \| null | User who created the comment. |
| `body` | string | Comment text. |
| `created_at` | string | ISO 8601 creation timestamp. |
| `updated_at` | string | ISO 8601 update timestamp. |

### Job

```json
{
  "id": "dc6d54d2-f6ac-4a87-9d54-12e93243db4e",
  "user": {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "u_2d9f6b1a",
    "is_admin": true,
    "created_at": "2026-05-15T10:30:00Z",
    "updated_at": "2026-05-15T10:30:00Z"
  },
  "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
  "job_type": "summarise",
  "status": "queued",
  "input": {
    "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
    "operation": "summarise"
  },
  "result": {},
  "error": null,
  "created_at": "2026-05-15T10:45:00Z",
  "updated_at": "2026-05-15T10:45:00Z",
  "started_at": null,
  "finished_at": null
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique job ID. |
| `user` | object | User who created the job. |
| `note_id` | string \| null | Related note ID, when the job is note-specific. |
| `job_type` | string | Job type, for example `summarise`, `structure`, `extract`, or `rewrite`. |
| `status` | string | Job status: `queued`, `running`, `succeeded`, `failed`, or `cancelled`. |
| `input` | object | Job input payload. |
| `result` | object | Job result payload. Empty until the job succeeds. |
| `error` | string \| null | Error message when the job fails. |
| `created_at` | string | ISO 8601 creation timestamp. |
| `updated_at` | string | ISO 8601 update timestamp. |
| `started_at` | string \| null | ISO 8601 start timestamp. |
| `finished_at` | string \| null | ISO 8601 finish timestamp. |

## Health

Returns service health and storage configuration.

### Endpoint

`GET /api/health`

### Authentication

None.

### Request

No request body.

### Response

```json
{
  "status": "ok",
  "service": "mianotes-web-service",
  "version": "0.1.0",
  "storage": {
    "data_dir": "data",
    "database_url": "sqlite:///mianotes.db"
  }
}
```

### Response fields

| Field | Type | Description |
|---|---|---|
| `status` | string | Health status. |
| `service` | string | Service identifier. |
| `version` | string | App version. |
| `storage.data_dir` | string | Configured note data directory. |
| `storage.database_url` | string | Redacted database URL. |

## Check email

Checks whether an email address belongs to an existing user and whether this is
the first user setup flow.

### Endpoint

`POST /api/auth/check-email`

### Authentication

None.

### Request

```json
{
  "email": "matt@example.com"
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `email` | string | Yes | Email address to check. |

### Response

First user setup:

```json
{
  "user_id": null,
  "is_first_user": true
}
```

Unknown user after household setup:

```json
{
  "user_id": null
}
```

Existing user:

```json
{
  "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d"
}
```

### Response fields

| Field | Type | Description |
|---|---|---|
| `user_id` | string \| null | Existing user ID, or `null` if the email is not registered. |
| `is_first_user` | boolean | Present only when no household has been initialized. |

## Join

Creates a user and starts a browser session. If no household exists yet, this
endpoint creates the first admin user and stores the household password.

### Endpoint

`POST /api/auth/join`

### Authentication

None.

### Request

```json
{
  "email": "matt@example.com",
  "name": "Matt",
  "password": "house-password",
  "password_confirmation": "house-password"
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `email` | string | Yes | New user's email address. |
| `name` | string | Yes | New user's display name. |
| `password` | string | Yes | Household password. |
| `password_confirmation` | string | First user only | Confirmation for the first household password. |

### Response

```json
{
  "user": {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "u_2d9f6b1a",
    "is_admin": true,
    "created_at": "2026-05-15T10:30:00Z",
    "updated_at": "2026-05-15T10:30:00Z"
  }
}
```

The response sets an HTTP-only `mianotes_session` cookie.

### Response fields

| Field | Type | Description |
|---|---|---|
| `user` | object | Created and signed-in user. |

### Error responses

| Status | Reason |
|---:|---|
| `400` | Password confirmation is missing or does not match during first setup. |
| `401` | Household password is invalid. |
| `409` | Email already exists. |
| `422` | Request validation failed. |

## Login

Starts a browser session for an existing user.

### Endpoint

`POST /api/auth/login`

### Authentication

None.

### Request

```json
{
  "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
  "password": "house-password"
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `user_id` | string | Yes | Existing user ID. |
| `password` | string | Yes | Household password. |

### Response

```json
{
  "user": {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "u_2d9f6b1a",
    "is_admin": true,
    "created_at": "2026-05-15T10:30:00Z",
    "updated_at": "2026-05-15T10:30:00Z"
  }
}
```

The response sets an HTTP-only `mianotes_session` cookie.

### Error responses

| Status | Reason |
|---:|---|
| `401` | User does not exist or password is invalid. |
| `422` | Request validation failed. |

## Get current session

Returns the current browser or bearer-token user.

### Endpoint

`GET /api/auth/session`

### Authentication

Session cookie or bearer token.

### Response

```json
{
  "user": {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "u_2d9f6b1a",
    "is_admin": true,
    "created_at": "2026-05-15T10:30:00Z",
    "updated_at": "2026-05-15T10:30:00Z"
  }
}
```

### Error responses

| Status | Reason |
|---:|---|
| `401` | No valid session cookie or bearer token. |

## Logout

Clears the browser session cookie.

### Endpoint

`POST /api/auth/logout`

### Authentication

None.

### Response

`204 No Content`

## Create API token

Creates a scoped API token for agents and automation scripts.

### Endpoint

`POST /api/tokens`

### Authentication

Session cookie or bearer token with `tokens:write` or `admin`.

### Request

```json
{
  "name": "Research agent",
  "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
  "scopes": ["notes:read", "notes:write", "topics:read"],
  "expires_at": null
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `name` | string | Yes | Human-readable token name. |
| `user_id` | string \| null | No | User to create the token for. Defaults to the current user. Only admins can create tokens for another user. |
| `scopes` | string[] | No | Token scopes. Defaults to `["notes:read"]`. |
| `expires_at` | string \| null | No | Optional ISO 8601 expiry timestamp. |

Supported scopes:

```text
admin
users:read
topics:read
topics:write
notes:read
notes:write
comments:write
tags:read
tags:write
share:write
tokens:read
tokens:write
```

### Response

```json
{
  "id": "1c9a26a9-d144-4f3e-91a7-a1121cfe0d4f",
  "user": {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "u_2d9f6b1a",
    "is_admin": true,
    "created_at": "2026-05-15T10:30:00Z",
    "updated_at": "2026-05-15T10:30:00Z"
  },
  "name": "Research agent",
  "token_prefix": "mia_w1x2y3z4",
  "scopes": ["notes:read", "notes:write", "topics:read"],
  "created_at": "2026-05-15T11:00:00Z",
  "updated_at": "2026-05-15T11:00:00Z",
  "last_used_at": null,
  "expires_at": null,
  "revoked_at": null,
  "token": "mia_w1x2y3z4_full_token_value"
}
```

### Response fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique token ID. |
| `user` | object | User who owns the token. |
| `name` | string | Human-readable token name. |
| `token_prefix` | string | Short token prefix for identification. |
| `scopes` | string[] | Scopes granted to the token. |
| `created_at` | string | ISO 8601 creation timestamp. |
| `updated_at` | string | ISO 8601 update timestamp. |
| `last_used_at` | string \| null | Timestamp when the token was last used. |
| `expires_at` | string \| null | Token expiry timestamp. |
| `revoked_at` | string \| null | Token revocation timestamp. |
| `token` | string | Raw bearer token. Returned only once at creation time. |

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `tokens:write`, or non-admin user tries to create a token for another user. |
| `404` | `user_id` does not exist. |
| `422` | Unsupported scope or request validation failed. |

## List API tokens

Lists API tokens for the current user, or for another user when called by an
admin.

### Endpoint

`GET /api/tokens`

### Authentication

Session cookie or bearer token with `tokens:read` or `admin`.

### Query parameters

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `user_id` | string | No | User whose tokens should be listed. Defaults to the current user. |
| `include_revoked` | boolean | No | Include revoked tokens. Defaults to `false`. |

### Response

```json
[
  {
    "id": "1c9a26a9-d144-4f3e-91a7-a1121cfe0d4f",
    "user": {
      "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
      "email": "matt@example.com",
      "name": "Matt",
      "username": "u_2d9f6b1a",
      "is_admin": true,
      "created_at": "2026-05-15T10:30:00Z",
      "updated_at": "2026-05-15T10:30:00Z"
    },
    "name": "Research agent",
    "token_prefix": "mia_w1x2y3z4",
    "scopes": ["notes:read", "notes:write"],
    "created_at": "2026-05-15T11:00:00Z",
    "updated_at": "2026-05-15T11:00:00Z",
    "last_used_at": "2026-05-15T11:05:00Z",
    "expires_at": null,
    "revoked_at": null
  }
]
```

The raw token value is not returned by this endpoint.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `tokens:read`, or non-admin user tries to list another user's tokens. |

## Revoke API token

Revokes an API token. Revoked tokens cannot be used again.

### Endpoint

`DELETE /api/tokens/{token_id}`

### Authentication

Session cookie or bearer token with `tokens:write` or `admin`.

### Path parameters

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `token_id` | string | Yes | API token ID. |

### Response

`204 No Content`

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `tokens:write`, or non-admin user tries to revoke another user's token. |
| `404` | Token does not exist. |

## Create user

Creates a user directly. Normal users usually join through `/api/auth/join`;
this endpoint is for admin-managed user creation.

### Endpoint

`POST /api/users`

### Authentication

Admin session or bearer token with `admin`.

### Request

```json
{
  "email": "emily.davis@example.com",
  "name": "Emily Davis"
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `email` | string | Yes | User email address. |
| `name` | string | Yes | User display name. |

### Response

Returns a `User`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Admin access required. |
| `409` | Email already exists. |
| `422` | Request validation failed. |

## List users

Lists all users.

### Endpoint

`GET /api/users`

### Authentication

Session cookie or bearer token with `users:read` or `admin`.

### Response

```json
[
  {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "u_2d9f6b1a",
    "is_admin": true,
    "created_at": "2026-05-15T10:30:00Z",
    "updated_at": "2026-05-15T10:30:00Z"
  }
]
```

## Get user

Returns one user.

### Endpoint

`GET /api/users/{user_id}`

### Authentication

Session cookie or bearer token with `users:read` or `admin`.

### Path parameters

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `user_id` | string | Yes | User ID. |

### Response

Returns a `User`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `users:read`. |
| `404` | User does not exist. |

## Update user

Updates a user's email or display name.

### Endpoint

`PATCH /api/users/{user_id}`

### Authentication

Admin session or bearer token with `admin`.

### Request

```json
{
  "email": "emily.davis@example.com",
  "name": "Emily Davis"
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `email` | string | No | Replacement email address. |
| `name` | string | No | Replacement display name. |

### Response

Returns the updated `User`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Admin access required. |
| `404` | User does not exist. |
| `409` | Email already exists. |
| `422` | Request validation failed. |

## Delete user

Deletes a user.

### Endpoint

`DELETE /api/users/{user_id}`

### Authentication

Admin session or bearer token with `admin`.

### Response

`204 No Content`

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Admin access required. |
| `404` | User does not exist. |

## Create topic

Creates a household-visible topic owned by the current user.

### Endpoint

`POST /api/topics`

### Authentication

Session cookie or bearer token with `topics:write` or `admin`.

### Request

```json
{
  "name": "School"
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `name` | string | Yes | Topic name. |
| `user_id` | string \| null | No | Accepted by schema but currently ignored; the topic owner is always the current user. |

### Response

Returns a `Topic`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `topics:write`. |
| `409` | Current user already has a topic with this name. |
| `422` | Request validation failed. |

## List topics

Lists topics, optionally filtered by owner.

### Endpoint

`GET /api/topics`

### Authentication

Session cookie or bearer token with `topics:read` or `admin`.

### Query parameters

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `user_id` | string | No | Return topics created by a specific user. |
| `include_archived` | boolean | No | Include archived topics. Defaults to `false`. |

### Response

```json
[
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
]
```

## Get topic

Returns one topic.

### Endpoint

`GET /api/topics/{topic_id}`

### Authentication

Session cookie or bearer token with `topics:read` or `admin`.

### Response

Returns a `Topic`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `topics:read`. |
| `404` | Topic does not exist. |

## Archive topic

Archives a topic. Archived topics are hidden from list responses unless
`include_archived=true`.

### Endpoint

`DELETE /api/topics/{topic_id}`

### Authentication

Session cookie or bearer token with `topics:write` or `admin`.

### Authorization

Admins can archive any topic. Normal users can archive only topics they created.

### Response

`204 No Content`

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `topics:write`, or user does not own the topic. |
| `404` | Topic does not exist. |

## Create note from text

Creates a Markdown note from plain text.

### Endpoint

`POST /api/notes/from-text`

`POST /api/notes` is an alias for this endpoint.

### Authentication

Session cookie or bearer token with `notes:write` or `admin`.

### Request

```json
{
  "topic_id": "f054964b-419b-419a-87df-de668025b0e3",
  "title": "Kickoff notes",
  "text": "We agreed to build Mianotes as a filesystem-first AI note app.",
  "tags": ["research", "planning"]
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `topic_id` | string | Yes | Topic ID for the note. |
| `text` | string | Yes | Source text. |
| `title` | string \| null | No | Optional title. If omitted, the API infers one from the text. |
| `tags` | string[] | No | Tags to attach. Maximum 5 tags per note. |
| `user_id` | string \| null | No | Accepted by schema but currently ignored; note owner is always the current user. |

### Response

Returns a full `Note`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `notes:write`. |
| `404` | Topic does not exist or is archived. |
| `422` | Request validation failed, including more than 5 tags. |

## Create note from file

Uploads a source file and creates a `pending_parse` note. The parser pipeline is
not wired into note generation yet.

### Endpoint

`POST /api/notes/from-file`

### Authentication

Session cookie or bearer token with `notes:write` or `admin`.

### Request

`multipart/form-data`

| Field | Type | Required | Description |
|---|---|---:|---|
| `topic_id` | string | Yes | Topic ID for the note. |
| `file` | file | Yes | Source file to upload. |
| `title` | string | No | Optional note title. If omitted, the API infers one from the filename. |

### Supported file extensions

```text
.csv
.doc
.docx
.html
.htm
.jpeg
.jpg
.md
.markdown
.odt
.pdf
.png
.rtf
.tif
.tiff
.txt
```

### Response

Returns a full `Note` with `status` set to `pending_parse`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `notes:write`. |
| `404` | Topic does not exist or is archived. |
| `415` | Unsupported file type. |
| `422` | File or form field validation failed. |

## List notes

Lists note metadata. The response does not include full Markdown text.

### Endpoint

`GET /api/notes`

### Authentication

Session cookie or bearer token with `notes:read` or `admin`.

### Query parameters

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `user_id` | string | No | Return notes created by a specific user. |
| `topic_id` | string | No | Return notes in a specific topic. |

### Response

```json
[
  {
    "id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
    "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "topic_id": "f054964b-419b-419a-87df-de668025b0e3",
    "title": "Kickoff notes",
    "status": "ready",
    "source_type": "text",
    "revision_number": 1,
    "is_published": false,
    "note_path": "/home/arduino/mianotes-web-service/data/u_2d9f6b1a/school/4a95f146-9d27-4c79-b7d8-34739aef8998.md",
    "created_at": "2026-05-15T10:35:00Z",
    "updated_at": "2026-05-15T10:35:00Z"
  }
]
```

## Get note

Returns a full note.

### Endpoint

`GET /api/notes/{note_id}`

### Authentication

Session cookie or bearer token with `notes:read` or `admin`.

### Response

Returns a full `Note`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `notes:read`. |
| `404` | Note does not exist. |

## Update note

Updates note title, Markdown text, publication state, or tags.

### Endpoint

`PATCH /api/notes/{note_id}`

### Authentication

Session cookie or bearer token with `notes:write` or `admin`.

### Authorization

Admins can update any note. Normal users can update only notes they created.

### Request

```json
{
  "title": "Updated kickoff notes",
  "text": "Updated Markdown text.",
  "is_published": true,
  "tags": ["planning", "ai"]
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `title` | string \| null | No | Replacement note title. |
| `text` | string \| null | No | Replacement Markdown text. |
| `is_published` | boolean \| null | No | Publication state. |
| `tags` | string[] \| null | No | Replacement tag set. Maximum 5 tags. |

### Response

Returns the updated full `Note`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `notes:write`, or user cannot change the note. |
| `404` | Note does not exist. |
| `422` | Request validation failed. |

## Delete note

Deletes a note, its stored Markdown file, source files, and related comments.

### Endpoint

`DELETE /api/notes/{note_id}`

### Authentication

Session cookie or bearer token with `notes:write` or `admin`.

### Authorization

Admins can delete any note. Normal users can delete only notes they created.

### Response

`204 No Content`

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `notes:write`, or user cannot delete the note. |
| `404` | Note does not exist. |

## Create Mia note job

Creates a queued Mia job for a note. These endpoints do not call OpenAI yet.

### Endpoints

```text
POST /api/notes/{note_id}/summarise
POST /api/notes/{note_id}/structure
POST /api/notes/{note_id}/extract
POST /api/notes/{note_id}/rewrite
```

### Authentication

Session cookie or bearer token with `notes:write` or `admin`.

### Authorization

Admins can create jobs for any note. Normal users can create jobs only for notes
they created.

### Request

No request body.

### Response

`202 Accepted`

Returns a `Job`.

```json
{
  "id": "dc6d54d2-f6ac-4a87-9d54-12e93243db4e",
  "user": {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "u_2d9f6b1a",
    "is_admin": true,
    "created_at": "2026-05-15T10:30:00Z",
    "updated_at": "2026-05-15T10:30:00Z"
  },
  "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
  "job_type": "summarise",
  "status": "queued",
  "input": {
    "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
    "operation": "summarise"
  },
  "result": {},
  "error": null,
  "created_at": "2026-05-15T10:45:00Z",
  "updated_at": "2026-05-15T10:45:00Z",
  "started_at": null,
  "finished_at": null
}
```

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `notes:write`, or user cannot change the note. |
| `404` | Note does not exist. |

## Share note

Creates or replaces a read-only share URL for a note.

### Endpoint

`POST /api/notes/{note_id}/share`

### Authentication

Session cookie or bearer token with `share:write` or `admin`.

### Authorization

Admins can share any note. Normal users can share only notes they created.

### Request

No request body.

### Response

```json
{
  "share_url": "http://127.0.0.1:8200/api/notes/shared/NAC0tW5f..."
}
```

### Response fields

| Field | Type | Description |
|---|---|---|
| `share_url` | string | Guest-readable URL for the shared note. |

## Disable note sharing

Revokes a note's share URL.

### Endpoint

`DELETE /api/notes/{note_id}/share`

### Authentication

Session cookie or bearer token with `share:write` or `admin`.

### Response

`204 No Content`

## Get shared note

Returns a shared note without requiring a session or bearer token.

### Endpoint

`GET /api/notes/shared/{token}`

### Authentication

None.

### Response

Returns a full `Note`.

### Error responses

| Status | Reason |
|---:|---|
| `404` | Share token is invalid or sharing has been disabled. |

## Get shared source file

Returns a source file attached to a shared note.

### Endpoint

`GET /api/notes/shared/{token}/files/{source_file_id}`

### Authentication

None.

### Response

Returns the stored file bytes.

### Error responses

| Status | Reason |
|---:|---|
| `404` | Share token, source file, or stored file does not exist. |

## List tags

Lists global tags.

### Endpoint

`GET /api/tags`

### Authentication

Session cookie or bearer token with `tags:read` or `admin`.

### Response

```json
[
  {
    "id": "d4fb05d7-3c77-4800-b3f9-1708ed8b7307",
    "name": "Research",
    "slug": "research",
    "created_at": "2026-05-15T10:35:00Z",
    "updated_at": "2026-05-15T10:35:00Z"
  }
]
```

## Replace note tags

Replaces the full tag set for a note. Send fewer tags to remove tags, or an
empty list to clear all tags.

### Endpoint

`PUT /api/notes/{note_id}/tags`

### Authentication

Session cookie or bearer token with `tags:write` or `admin`.

### Authorization

Admins can change tags for any note. Normal users can change tags only for notes
they created.

### Request

```json
{
  "tags": ["research", "planning"]
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `tags` | string[] | No | Replacement tag set. Maximum 5 tags per note. |

### Response

Returns the updated full `Note`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `tags:write`, or user cannot change the note. |
| `404` | Note does not exist. |
| `422` | More than 5 tags or request validation failed. |

## List comments

Lists comments for a note.

### Endpoint

`GET /api/notes/{note_id}/comments`

### Authentication

Session cookie or bearer token with `notes:read` or `admin`.

### Response

```json
[
  {
    "id": "0ebd5d0d-b40c-4084-aeb4-cf687ab81922",
    "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
    "user": {
      "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
      "email": "matt@example.com",
      "name": "Matt",
      "username": "u_2d9f6b1a",
      "is_admin": true,
      "created_at": "2026-05-15T10:30:00Z",
      "updated_at": "2026-05-15T10:30:00Z"
    },
    "body": "This is useful for the next call.",
    "created_at": "2026-05-15T10:40:00Z",
    "updated_at": "2026-05-15T10:40:00Z"
  }
]
```

## Create comment

Creates a comment for a note.

### Endpoint

`POST /api/notes/{note_id}/comments`

### Authentication

Session cookie or bearer token with `comments:write` or `admin`.

### Request

```json
{
  "body": "This is useful for the next call."
}
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `body` | string | Yes | Comment text. |

### Response

Returns a `Comment`.

## Update comment

Updates a comment body.

### Endpoint

`PATCH /api/notes/{note_id}/comments/{comment_id}`

### Authentication

Session cookie or bearer token with `comments:write` or `admin`.

### Authorization

Admins can update any comment. Normal users can update only comments they
created.

### Request

```json
{
  "body": "Updated comment text."
}
```

### Response

Returns the updated `Comment`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `comments:write`, or user cannot change the comment. |
| `404` | Note or comment does not exist. |
| `422` | Request validation failed. |

## Delete comment

Deletes a comment.

### Endpoint

`DELETE /api/notes/{note_id}/comments/{comment_id}`

### Authentication

Session cookie or bearer token with `comments:write` or `admin`.

### Authorization

Admins can delete any comment. Normal users can delete only comments they
created.

### Response

`204 No Content`

## Search notes

Searches saved Markdown notes using ripgrep and joins matches back to note
metadata from SQLite.

### Endpoint

`GET /api/search`

### Authentication

Session cookie or bearer token with `notes:read` or `admin`.

### Query parameters

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `q` | string | Yes | Search query. Minimum length is 1. |
| `limit` | number | No | Maximum number of matches to return. Defaults to `50`. Maximum is `100`. |

### Request

```text
GET /api/search?q=product%20launch&limit=10
```

### Response

```json
[
  {
    "note": {
      "id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
      "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
      "topic_id": "f054964b-419b-419a-87df-de668025b0e3",
      "title": "Product launch meeting notes",
      "status": "ready",
      "source_type": "text",
      "revision_number": 1,
      "is_published": false,
      "note_path": "/home/arduino/mianotes-web-service/data/u_2d9f6b1a/work/4a95f146-9d27-4c79-b7d8-34739aef8998.md",
      "created_at": "2026-05-15T10:35:00Z",
      "updated_at": "2026-05-15T10:35:00Z"
    },
    "line_number": 12,
    "column": 8,
    "excerpt": "We discussed the product launch plan and next actions."
  }
]
```

### Response fields

| Field | Type | Description |
|---|---|---|
| `note` | object | Matching note metadata. |
| `line_number` | number | 1-based line number in the Markdown file. |
| `column` | number | 1-based column for the first match on the line. |
| `excerpt` | string | Matching line text. |

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `notes:read`. |
| `422` | Missing or invalid query parameters. |
| `503` | `ripgrep` is not installed or search failed. |

## List jobs

Lists Mia jobs visible to the current user. Admins can see all jobs. Normal
users see only their own jobs.

### Endpoint

`GET /api/jobs`

### Authentication

Session cookie or bearer token with `notes:read` or `admin`.

### Query parameters

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `note_id` | string | No | Return jobs related to a specific note. |
| `status` | string | No | Return jobs with a specific status. |

### Response

```json
[
  {
    "id": "dc6d54d2-f6ac-4a87-9d54-12e93243db4e",
    "user": {
      "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
      "email": "matt@example.com",
      "name": "Matt",
      "username": "u_2d9f6b1a",
      "is_admin": true,
      "created_at": "2026-05-15T10:30:00Z",
      "updated_at": "2026-05-15T10:30:00Z"
    },
    "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
    "job_type": "summarise",
    "status": "queued",
    "input": {
      "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
      "operation": "summarise"
    },
    "result": {},
    "error": null,
    "created_at": "2026-05-15T10:45:00Z",
    "updated_at": "2026-05-15T10:45:00Z",
    "started_at": null,
    "finished_at": null
  }
]
```

## Get job

Returns one Mia job.

### Endpoint

`GET /api/jobs/{job_id}`

### Authentication

Session cookie or bearer token with `notes:read` or `admin`.

### Response

Returns a `Job`.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `notes:read`, or user cannot read the job. |
| `404` | Job does not exist. |

## Get stored data file

Returns a stored Markdown or source file from the configured data directory.

### Endpoint

`GET /data/{file_path}`

### Authentication

Session cookie or bearer token with `notes:read` or `admin`.

### Path parameters

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `file_path` | string | Yes | Relative path under the configured data directory. |

### Response

Returns file bytes.

### Error responses

| Status | Reason |
|---:|---|
| `401` | Not authenticated. |
| `403` | Token lacks `notes:read`. |
| `404` | File does not exist or path escapes the data directory. |

## MCP server

Mianotes ships a stdio MCP server for compatible agents.

### Command

```bash
MIANOTES_API_URL=http://127.0.0.1:8200 \
MIANOTES_API_TOKEN=mia_your_token \
python -m mianotes_web_service.mcp_server
```

Fresh package installs also expose the `mianotes-mcp` console script.

### Authentication

The MCP server calls the REST API with `MIANOTES_API_TOKEN`. Normal API token
scopes still apply.

### Tools

```text
list_topics
create_topic
list_notes
get_note
create_note
update_note
add_comment
set_tags
search_notes
summarise_note
structure_note
extract_note
rewrite_note
```
