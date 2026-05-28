# Authentication and users

This page documents authentication, session, token, and user endpoints.

## Check email

```text
POST /api/auth/check-email
```

Authentication: none.

Request:

```json
{
  "email": "matt@example.com"
}
```

First user setup response:

```json
{
  "user_id": null,
  "is_first_user": true
}
```

Existing user response:

```json
{
  "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d"
}
```

## Join

```text
POST /api/auth/join
```

Authentication: none.

If no Mianotes workspace has been initialized, this endpoint creates the first admin user and stores the master password.

Request:

```json
{
  "email": "matt@example.com",
  "name": "Matt",
  "password": "house-password",
  "password_confirmation": "house-password"
}
```

The response sets an HTTP-only `mianotes_session` cookie.

## Login

```text
POST /api/auth/login
```

Authentication: none.

Request:

```json
{
  "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
  "password": "house-password"
}
```

The response sets an HTTP-only `mianotes_session` cookie.

## Get current session

```text
GET /api/auth/session
```

Authentication: session cookie or bearer token.

Example:

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/auth/session"
```

## Create agent session

```text
POST /api/auth/agent-session
```

Authentication: bearer API key or scoped API token.

Required headers:

```http
Authorization: Bearer <MIANOTES_API_KEY>
X-Mianotes-Client: Codex
```

Mianotes validates the bearer token, maps `X-Mianotes-Client` into a stable
client ID, signs that identity into a short-lived session token, and returns the
token for follow-up requests. Unknown client names default to `MCP`. The raw API
key is not embedded in the session token.

Response:

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "client_key": "codex",
  "client": "Codex",
  "expires_at": "2026-05-27T12:00:00Z",
  "user": {
    "id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
    "email": "matt@example.com",
    "name": "Matt",
    "username": "matt",
    "phone": null,
    "role": null,
    "photo_url": null,
    "is_admin": true
  },
  "scopes": ["admin"]
}
```

## Logout

```text
POST /api/auth/logout
```

Authentication: none.

Response: `204 No Content`.

## Create scoped API token

```text
POST /api/tokens
```

Authentication: session cookie or bearer token with `tokens:write` or `admin`.

Request:

```json
{
  "name": "Research agent",
  "user_id": "c5ddebcc-e434-4e1a-bc8a-48263eb0095d",
  "scopes": ["notes:read", "notes:write", "folders:read"],
  "expires_at": null
}
```

The raw token is returned only once.

## List API tokens

```text
GET /api/tokens
```

Authentication: session cookie or bearer token with `tokens:read` or `admin`.

Query parameters:

| Parameter | Description |
|---|---|
| `user_id` | Optional user whose tokens should be listed. Admin only for other users. |
| `include_revoked` | Include revoked tokens. Defaults to `false`. |

Raw token values are not returned by this endpoint.

## Revoke API token

```text
DELETE /api/tokens/{token_id}
```

Authentication: session cookie or bearer token with `tokens:write` or `admin`.

Response: `204 No Content`.

## Create service API key

```text
POST /api/settings/api-key
```

Authentication: admin session or bearer token with `admin`.

Creates the service-wide key used by local agents and MCP clients. The service
writes the raw key to its environment file and stores only a public verifier in
the active database.

Response:

```json
{
  "token": "mia_generated_service_key"
}
```

The raw key is returned only once. For the full web-app and direct API workflow,
see [API tokens](../04-for-agents/02-api-tokens.md).

## User endpoints

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `POST` | `/api/users` | Create a user directly | Admin |
| `GET` | `/api/users` | List users | `users:read` or admin |
| `GET` | `/api/users/{user_id}` | Get one user | `users:read` or admin |
| `PATCH` | `/api/users/{user_id}` | Update profile | profile owner or admin |
| `POST` | `/api/users/{user_id}/photo` | Upload profile photo | profile owner or admin |
| `DELETE` | `/api/users/{user_id}` | Delete user | Admin |

Profile photos accept JPG or PNG files, crop and resize to `200x200`, convert to JPEG, and store the resized image under `data/.profiles`.
