---
name: mianotes
description: Use when the user says Mia or Mianotes, asks to save, search, retrieve, update, or prompt notes, save the current answer as a note, create notes from text/files/URLs, or interact with the local Mianotes knowledge service from an agent.
---

# Mianotes

Mia means the local Mianotes knowledge service.

Use Mianotes when the user says things like:

- "Mia, save this as a note in Research"
- "Save your last answer to Mianotes"
- "Search Mia for the deployment notes"
- "Add this to the Project X notes"
- "Ask Mia to summarise this note"

## Connection

Prefer Mianotes MCP tools when available.

If MCP tools are not available, use the REST API:

- Default API URL: `http://127.0.0.1:8200`
- Override with `MIANOTES_API_URL`
- Authenticate with `MIANOTES_API_TOKEN`

Never hardcode tokens in files, docs, commits, or command examples that will be
saved.

## Saving Notes

When the user asks to save the current or previous assistant answer:

1. Identify the target project by name.
2. Fetch projects with `GET /api/projects`.
3. If one project matches, use it.
4. If no project matches, create it only when the user clearly asked for that project.
5. Create the note with `POST /api/notes/from-text`.
6. Use a short useful title.
7. Preserve the answer text as Markdown.

If the target project is ambiguous, ask a short clarification before saving.

## Searching Notes

When the user asks what Mia remembers, search notes first:

`GET /api/search?q=<query>`

Use matching note IDs to fetch full note content with:

`GET /api/notes/{note_id}`

## Prompting Mia

To ask Mia to process an existing note, post a comment starting with `@mia`:

`POST /api/notes/{note_id}/comments`

```json
{
  "body": "@mia summarise this text"
}
```

Mia prompt comments are synchronous. They return Markdown directly, do not
create jobs, do not save the prompt as a normal comment, and do not update the
note.

Only update a note with Mia's response when the user explicitly asks to save or
apply that response.

## Safety

Do not save secrets, API keys, passwords, private tokens, credentials, or
private personal data unless the user explicitly confirms.

For destructive actions such as deleting notes or archiving projects, ask for
confirmation unless the user clearly requested the exact action.
