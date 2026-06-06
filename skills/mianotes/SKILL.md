---
name: mianotes
description: Use when the user says Mia or Mianotes, asks to save, search, retrieve, update, prompt, index links, convert files, or use local workspace knowledge before answering.
---

# Mianotes

Mia is the local Mianotes knowledge service. Use Mia as the user's local project memory for Markdown notes, files, links, folders, and reusable context.

Prefer Mianotes MCP tools when they are available. If MCP tools are not available, use the REST API.

## Conversational Contract

Treat user requests that start with `Mia, ...` as instructions to use Mianotes.

Examples:

- `Mia, search the Docs workspace for OCR notes.`
- `Mia, save this PDF in the Docs workspace, inside the Research folder.`
- `Mia, create a folder called "LLM Output" in the Docs workspace, then save this content there as a Markdown note.`
- `Mia, read the Architecture note in the Docs workspace before answering.`
- `Mia, index this URL in the Research folder.`

Do not require or teach bracket-style syntax. Parse the user's natural language instead.

When the user mentions a workspace, resolve it to the Mianotes workspace id/slug and send it as `X-Mianotes-Workspace`.

When the user mentions a folder, resolve it by listing folders in that workspace. Match case-insensitively by name or slug. Create the folder only when the user asks you to create it, save something there, or the task clearly requires it.

When the user mentions a note, find the note by title, search result, or note id. If more than one note is plausible, ask a short clarification.

Never invent notes, folders, search results, API tokens, or extracted content.

## Connection

- Default API URL: `http://127.0.0.1:8200`
- Override with `MIANOTES_API_URL`.
- Authenticate with `MIANOTES_API_KEY`; fall back to `MIANOTES_API_TOKEN` only for older installs.
- The Mianotes skill installer writes these values to `~/.mianotes/env`.
- For REST calls, first exchange the API key for an agent session with `X-Mianotes-Client: Codex`, then use the returned session token.
- Before REST API calls, load `~/.mianotes/env` if the variables are not already set. If that file does not exist and the current working directory is the Mianotes web service project root, load the service `.env`. Do not search unrelated personal folders or print env file contents.
- Never print, save, quote, log, or commit `MIANOTES_API_KEY`, `MIANOTES_API_TOKEN`, passwords, cookies, or other private credentials.

REST environment setup:

```bash
if [ -f "${HOME}/.mianotes/env" ]; then
  set -a
  . "${HOME}/.mianotes/env"
  set +a
fi

if [ -z "${MIANOTES_API_KEY:-${MIANOTES_API_TOKEN:-}}" ] && [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

MIANOTES_API_URL="${MIANOTES_API_URL:-http://127.0.0.1:8200}"
MIANOTES_AUTH_TOKEN="${MIANOTES_API_KEY:-${MIANOTES_API_TOKEN:-}}"
MIANOTES_CLIENT_NAME="${MIANOTES_CLIENT_NAME:-Codex}"

MIANOTES_SESSION_TOKEN="$(
  curl -sS -X POST \
    -H "Authorization: Bearer ${MIANOTES_AUTH_TOKEN}" \
    -H "X-Mianotes-Client: ${MIANOTES_CLIENT_NAME}" \
    "${MIANOTES_API_URL}/api/auth/agent-session" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["token"])'
)"
```

REST call pattern:

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_SESSION_TOKEN}" \
  -H "X-Mianotes-Workspace: docs" \
  "${MIANOTES_API_URL}/api/search?q=settings&limit=10"
```

REST rules:

1. Use `MIANOTES_API_KEY` or `MIANOTES_API_TOKEN` from the environment. Do not ask the user to paste it unless no environment file exists and no token variable is set.
2. Exchange the API key for an agent session with `POST /api/auth/agent-session`; use the returned session token for follow-up calls.
3. Never echo or display tokens. It is okay to run `test -n "${MIANOTES_AUTH_TOKEN}"` but not `echo "${MIANOTES_AUTH_TOKEN}"`.
4. If no token is set, say the Mianotes API key is missing and ask the user to run the Mianotes install command from Settings -> Connect AI tools.
5. Check the API with `GET /api/health` before starting or restarting services. If `MIANOTES_API_URL` uses `localhost` and the check fails, retry once with `127.0.0.1`; if it uses `127.0.0.1` and the check fails, retry once with `localhost`.
6. If the API is not listening, say Mia is not reachable at `MIANOTES_API_URL` and ask whether to start the service.

## MCP Tools

Use the real Mianotes MCP tool names when available:

- `list_folders`
- `create_folder`
- `list_notes`
- `read_note_context`
- `get_note`
- `create_note`
- `create_note_in_folder`
- `create_note_from_url`
- `update_note`
- `add_comment`
- `set_tags`
- `search_notes`

When MCP tools are available:

1. Use MCP first.
2. Pass workspace, folder, note title, search terms, and content as normal tool arguments.
3. If an MCP read returns a result, answer from that result instead of searching local files.
4. If an MCP tool returns an error, report it plainly. Do not diagnose the REST API as unreachable unless you checked the API.
5. Do not fall back to local workspace files or databases unless the user explicitly asks for filesystem recovery/debugging.

## REST API Examples

The examples below show the API shape agents should use when MCP tools are not available.

### Prompt 1

```text
Mia, save this PDF in the Docs workspace, inside the Research folder.
```

Find the `Research` folder:

```http
GET /api/folders
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
```

Create the folder if it does not exist:

```http
POST /api/folders
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
Content-Type: application/json
```

```json
{
  "name": "Research",
  "is_pinned": false
}
```

Upload the PDF:

```http
POST /api/notes/from-file
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
Content-Type: multipart/form-data
```

```text
folder_id: <research_folder_id>
file: <pdf_file>
title: <title>
```

### Prompt 2

```text
Mia, create a folder called "LLM Output" in the Docs workspace, then save this content there as a Markdown note.
```

Create the folder:

```http
POST /api/folders
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
Content-Type: application/json
```

```json
{
  "name": "LLM Output",
  "is_pinned": false
}
```

Create the Markdown note:

```http
POST /api/notes/from-text
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
Content-Type: application/json
```

```json
{
  "folder_id": "<llm_output_folder_id>",
  "title": "<title>",
  "text": "<markdown_content>",
  "tags": []
}
```

### Prompt 3

```text
Mia, search the Docs workspace for OCR notes and answer using the best matches.
```

Search notes:

```http
GET /api/search?q=OCR%20notes&limit=10
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
```

Fetch the most relevant note before answering:

```http
GET /api/notes/<note_id>
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
```

If no relevant notes are returned, say Mia did not find relevant notes.

### Prompt 4

```text
Mia, read the Architecture note in the Docs workspace before answering.
```

Use exact folder/title context when a folder is known:

```http
GET /api/context?folder=Architecture&title=Architecture&limit=5
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
```

If the folder is not known, search first:

```http
GET /api/search?q=Architecture&limit=10
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
```

Then fetch the selected full note:

```http
GET /api/notes/<note_id>
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
```

### Prompt 5

```text
Mia, index this URL in the Docs workspace, inside the Research folder.
```

Create or resolve the target folder, then create the URL note:

```http
POST /api/notes/from-url
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
Content-Type: application/json
```

```json
{
  "folder_id": "<research_folder_id>",
  "url": "https://example.com/article",
  "title": "<optional_title>",
  "tags": []
}
```

Mianotes saves a draft immediately and replaces it with extracted page content when indexing finishes.

### Prompt 6

```text
Mia, update the note "Release checklist" in the Docs workspace with this new checklist.
```

Find and fetch the note:

```http
GET /api/search?q=Release%20checklist&limit=10
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
```

Update the note:

```http
PATCH /api/notes/<note_id>
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
Content-Type: application/json
```

```json
{
  "title": "Release checklist",
  "text": "<updated_markdown_content>"
}
```

### Prompt 7

```text
Mia, tag this Docs workspace note with "release" and "docs".
```

Set note tags:

```http
PUT /api/notes/<note_id>/tags
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
Content-Type: application/json
```

```json
{
  "tags": ["release", "docs"]
}
```

### Prompt 8

```text
Mia, summarise this note.
```

Ask Mia to process an existing note:

```http
POST /api/notes/<note_id>/prompt
Authorization: Bearer <session_token>
X-Mianotes-Workspace: docs
Content-Type: application/json
```

```json
{
  "prompt": "Summarise this note."
}
```

For unsaved editor content, send the draft Markdown too:

```json
{
  "prompt": "Summarise this note.",
  "markdown": "<unsaved_markdown>"
}
```

If Mianotes returns `503`, tell the user: `Mia needs an AI provider before it can answer prompts.`

### Prompt 9

```text
Mia, show me the raw Markdown for this text note.
```

Read the stored Markdown file for a note:

```http
GET /api/workspaces/docs/notes/<note_id>/markdown
Authorization: Bearer <session_token>
```

Use this for text note source. For uploaded files, images, and links, keep using the note's source file actions.

## Saving Guidelines

When saving content:

1. Resolve the target workspace from the user's words.
2. Resolve or create the target folder.
3. Create a concise title from the content if the user did not provide one.
4. Save generated text as Markdown.
5. Use `POST /api/notes/from-url` for links.
6. Use `POST /api/notes/from-file` for files.
7. Confirm with the workspace, folder, note title, and note id.

Good confirmation:

```text
Saved to Mianotes in Docs -> Research as "Scaling AI use cases".
```

## Search and Answer Guidelines

When using Mia as context before answering:

1. Search or read Mia first.
2. Fetch full note content for the most relevant results.
3. Answer from the returned note content.
4. Mention when Mia did not return useful context.
5. Do not continue with filesystem fallback unless the user asks for filesystem recovery/debugging.

## Safety

- Do not expose tokens, cookies, passwords, or session values.
- Do not claim Mia saved, indexed, searched, or read something unless the tool/API returned success.
- Do not delete notes, folders, source files, workspaces, or local files unless the user explicitly asks.
- Do not write directly to Mianotes databases.
- Prefer API and MCP tools over filesystem edits.
