# Comments

Comments are attached to notes and are visible to signed-in users with note read
access.

Most comments are normal saved discussion:

```json
{
  "body": "This is useful for the next call."
}
```

The API saves the comment and returns:

```json
{
  "type": "comment",
  "id": "0ebd5d0d-b40c-4084-aeb4-cf687ab81922",
  "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
  "body": "This is useful for the next call.",
  "created_at": "2026-05-15T10:40:00Z",
  "updated_at": "2026-05-15T10:40:00Z"
}
```

## Prompting Mia

If a comment starts with `@mia`, the backend treats it as a Mia prompt. The
prompt is still saved as a comment so other users and agents can see what was
asked and reuse the prompt later:

```json
{
  "body": "@mia summarise this text"
}
```

Mianotes strips the `@mia` prefix, reads the current note Markdown, sends the
prompt and note content to the configured LLM provider, and waits for the
response.

The response is returned directly:

```json
{
  "type": "prompt",
  "prompt": "summarise this text",
  "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
  "text": "## Summary\n\nThe note explains the Mallorca trip plan...",
  "comment": {
    "type": "comment",
    "id": "0ebd5d0d-b40c-4084-aeb4-cf687ab81922",
    "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
    "body": "@mia summarise this text",
    "created_at": "2026-05-15T10:40:00Z",
    "updated_at": "2026-05-15T10:40:00Z"
  },
  "format": "markdown"
}
```

Prompt comments:

- are synchronous
- do not create jobs
- are saved as comments with the original `@mia` body
- do not update the note
- return Markdown only

The frontend can show a loader while the request is running, then display
`text` in a modal. If the user likes Mia's answer, the frontend can update the
note with `PATCH /api/notes/{note_id}`. If the user closes the modal, nothing
changes.

Agents use the same flow. An agent can send an `@mia` comment, read the returned
Markdown, then decide whether to update the note.

## Error handling

An empty Mia prompt returns `422`:

```json
{
  "detail": "Mia prompt cannot be empty"
}
```

If Mia is not configured, or the configured LLM provider is unavailable, the API
returns `503`.
