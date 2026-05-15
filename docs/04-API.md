# APIs

All API responses are JSON unless an endpoint returns a stored file.

The REST API is part of the product surface. Humans use it indirectly through
the web app. AI agents and automation scripts can use it directly. A future MCP
server should expose the same core capabilities as tools.

## Auth

```text
POST /api/auth/check-email
POST /api/auth/join
POST /api/auth/login
GET  /api/auth/session
POST /api/auth/logout
```

Sessions use HTTP-only cookies. The backend decides whether a `join` request creates the first admin or a normal user.

Browser sessions are for the web app. Agent access should use scoped API tokens
instead of cookies.

## API tokens

Agents and automation scripts authenticate with bearer tokens:

```text
Authorization: Bearer mia_<token>
```

Token management endpoints:

```text
POST   /api/tokens
GET    /api/tokens
DELETE /api/tokens/{token_id}
```

`POST /api/tokens` returns the raw token only once. The database stores only a
hash, prefix, owner, scope list, and lifecycle metadata.

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

Browser sessions bypass scope checks because they represent an interactive
household user. Bearer tokens must include the relevant scope, or `admin`, for
each protected API.

## Users

```text
GET    /api/users
GET    /api/users/{user_id}
POST   /api/users
PATCH  /api/users/{user_id}
DELETE /api/users/{user_id}
```

User creation, updates, and deletion require admin access.

## Topics

```text
GET    /api/topics
POST   /api/topics
GET    /api/topics/{topic_id}
DELETE /api/topics/{topic_id}
```

Topic deletion archives the topic. Any signed-in user can create a topic. Only the topic creator or an admin can archive it.

## Notes

```text
GET    /api/notes
POST   /api/notes
POST   /api/notes/from-text
POST   /api/notes/from-file
GET    /api/notes/{note_id}
PATCH  /api/notes/{note_id}
DELETE /api/notes/{note_id}
```

Notes include metadata such as `status`, `source_type`, `revision_number`, `is_published`, `created_at`, and `updated_at`.

Planned Mia/agent operations should build on the note API instead of bypassing
it:

```text
POST /api/notes/{note_id}/summarise
POST /api/notes/{note_id}/structure
POST /api/notes/{note_id}/extract
POST /api/notes/{note_id}/rewrite
```

These operations can be asynchronous once parsing and model calls are wired in.

## Tags

```text
GET /api/tags
PUT /api/notes/{note_id}/tags
```

Tags are global to the household instance and can be attached to many notes.
Use `PUT /api/notes/{note_id}/tags` to replace the full tag set for a note. Send fewer tags to remove tags, or an empty list to clear them. A note can have at most 5 tags.

## Comments

```text
GET    /api/notes/{note_id}/comments
POST   /api/notes/{note_id}/comments
PATCH  /api/notes/{note_id}/comments/{comment_id}
DELETE /api/notes/{note_id}/comments/{comment_id}
```

Comments are stored in SQLite, not sidecar JSON files.

## Sharing

```text
POST   /api/notes/{note_id}/share
DELETE /api/notes/{note_id}/share
GET    /api/notes/shared/{token}
GET    /api/notes/shared/{token}/files/{source_file_id}
```

Share links are random, revocable, and read-only. A valid share token grants access to one note, not the full household.

## Future MCP tools

The MCP server should expose Mianotes as tools AI agents can call:

```text
list_topics
create_topic
list_notes
get_note
create_note
update_note
add_comment
set_tags
share_note
search_notes
ask_mia
```
