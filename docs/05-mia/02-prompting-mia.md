# Prompting Mia

Mia is prompted through the comments endpoint.

If a comment request body starts with `@mia`, Mianotes treats it as a private Mia prompt instead of a shared comment.

## Endpoint

```text
POST /api/notes/{note_id}/comments
```

Authentication:

```text
Session cookie or bearer token with comments:write or admin
```

## Request

```json
{
  "body": "@mia summarise this note"
}
```

Mianotes strips the `@mia` prefix, reads the current note Markdown, sends the prompt and note content to the configured LLM provider, and waits for the response.

## Response

```json
{
  "type": "prompt",
  "prompt": "summarise this note",
  "note_id": "4a95f146-9d27-4c79-b7d8-34739aef8998",
  "text": "## Summary\n\nThe note explains the Mallorca trip plan...",
  "format": "markdown"
}
```

## Important behaviour

Mia prompts:

- are synchronous;
- do not create jobs;
- are private;
- are not saved as comments;
- are not returned by `GET /api/notes/{note_id}/comments`;
- do not update the note;
- return Markdown only.

If you want Mia's answer to become part of the note, copy the returned Markdown into an update request or paste it in the web app.

## Example prompts

```text
@mia summarise this note for a project manager
@mia extract the tasks, owners, and dates
@mia rewrite this as clear documentation
@mia list unanswered questions in this note
@mia turn this into revision notes with definitions and examples
@mia find security-sensitive content in this note
```

## Errors

An empty Mia prompt returns `422`:

```json
{
  "detail": "Mia prompt cannot be empty"
}
```

If Mia is not configured, or the configured LLM provider is unavailable, the API returns `503`.

## Prompting style

Good prompts are specific about the output format.

Good:

```text
@mia rewrite this note as a concise implementation guide with headings: Goal, Setup, Steps, Common errors, Next steps.
```

Weak:

```text
@mia improve this
```
