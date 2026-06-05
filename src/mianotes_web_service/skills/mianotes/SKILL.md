---
name: mianotes
description: Use when the user says Mia or Mianotes, asks to save, search, retrieve, update, prompt, index links, convert files, or use local folder knowledge before answering.
---

# Mianotes

Mia is the local Mianotes knowledge service. Use Mia as the user's local project memory for Markdown notes, files, links, folders, and reusable context.

Prefer Mianotes MCP tools when available. If MCP tools are not available, use the REST API.

## MCP Contract

When Mianotes MCP tools are available, treat MCP as the source of truth.

Hard rules:

1. For `Mia(workspace: ..., folder: ..., note: ...)`, call `read_note_context` first.
2. If `read_note_context` returns `total > 0`, use `results[0].text` as the note content and answer from that content. Do not call REST, do not inspect local files, do not search the filesystem, and do not claim Mia failed.
3. If `read_note_context` returns `total: 0`, say Mia did not find that note. Do not hallucinate a substitute note.
4. For `Mia(workspace: ..., folder: ...)`, read or search within that workspace folder, unless the user is clearly asking to save new content there.
5. For `Mia(workspace: ...)`, read or search within that workspace, unless the user is clearly asking to save new content there.
6. If an MCP tool returns an error, report the MCP error plainly. Do not diagnose the API as unreachable unless you actually checked the API health endpoint.
7. Do not fall back to local workspace files or databases unless the user explicitly asks for filesystem recovery/debugging.
8. Never continue searching after a successful exact MCP read unless the user asked for broader context.

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

REST call rules:

1. Always use `MIANOTES_API_KEY` or `MIANOTES_API_TOKEN` from the environment; never ask the user to paste it unless no `.env` exists and no token variable is set.
2. Exchange the API key for an agent session with `POST /api/auth/agent-session` and `X-Mianotes-Client: Codex`; use the returned session token for follow-up calls.
3. Never echo or display tokens. It is okay to run `test -n "${MIANOTES_AUTH_TOKEN}"` but not `echo "${MIANOTES_AUTH_TOKEN}"`.
4. If no token is set, say the Mianotes API key is missing and ask the user to run the Mianotes skill install command from Settings.
5. Check the API with `GET /api/health` before starting or restarting services. If `MIANOTES_API_URL` uses `localhost` and the check fails, retry once with `127.0.0.1`; if it uses `127.0.0.1` and the check fails, retry once with `localhost`.
6. If the API is not listening, do not spend a long time rediscovering the app. Say Mia is not reachable at `MIANOTES_API_URL` and ask whether to start the service.

REST curl pattern:

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_SESSION_TOKEN}" \
  "${MIANOTES_API_URL}/api/search?q=settings&limit=10"
```

## Available MCP Tools

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

## When to Use Mia

Use Mia when the user asks to:

- save content as a note
- save your last answer
- search saved notes
- retrieve context before answering
- index a link
- convert or save a file
- update or append to an existing note
- create or update a task list
- ask Mia to summarise, extract, rewrite, humanize, or improve a note

Examples:

- "Mia, save this as a note in Research"
- "Save your last answer to Mianotes"
- "Search Mia for the deployment notes"
- "Look in Mianotes first"
- "Before answering, ask Mia for context"
- "Index this page in Mia"
- "Convert this PDF and save it under Work"
- "Update the Work to-do list"

## Search Commands

Trigger search when the user says things like:

- "Search Mia for deployment notes"
- "Find my notes about Docker"
- "Look in Mianotes for the API docs"
- "What did I save about authentication?"
- "Do I have anything in Mia about this?"
- "Search my notes for this"
- "Search the local knowledge base"
- "Ask Mia what we know about this"
- "Ask Mia for context"
- "Use Mia to provide context"
- "Check Mia before answering"
- "Look in Work for notes about OCR"
- "Find the note where I mentioned Tesseract"
- "Search Work for the remaining tasks"
- "Show me notes related to this project"

Expected behavior:

1. Query Mia with the user's search terms.
2. If a folder is named, scope the search or filter results to that folder when possible.
3. Return the most relevant note titles, excerpts, and IDs.
4. If the user asks a question, fetch the most relevant full notes and use them as context before answering.
5. If nothing useful is found, say that Mia did not return relevant notes and continue with the best available context.

REST fallback:

- Search: `GET /api/search?q=<query>&limit=<n>`
- Fetch full note: `GET /api/notes/{note_id}`

Do not invent search results or imply Mia knows something that was not returned.

## Context Shorthand

Mia supports three context shorthand forms:

```text
Mia(workspace: ..., folder: ..., note: ...)
Mia(workspace: ..., folder: ...)
Mia(workspace: ...)
```

Use the most specific form the user provided. Do not invent missing folder or note names.

### Exact Note Context

When the user writes `Mia(workspace: ..., folder: ..., note: ...)`, treat it as an explicit request to retrieve that note before continuing.

Examples:

- "Before answering, get context from Mia(workspace: Docs, folder: About, note: Use Cases)."
- "Read Mia(workspace: Mianotes, folder: Getting Started, note: Installation) first."
- "Use Mia(workspace: My App, folder: Architecture, note: System overview) as source context."

Expected behavior:

1. Use the MCP `read_note_context` tool when it is available.
2. Pass the workspace name exactly as the user wrote it. Do not silently change `Docs` to `docs` unless Mia returns a workspace-not-found error and you are retrying once.
3. Pass the folder name and note title exactly as the user wrote them.
4. If the tool returns one or more results, use `results[0].text` as the note content.
5. Stop tool use after the exact note is returned, unless the user asked for broader context.
6. Include a short phrase or specific detail from the note when useful, so the user can see Mia was actually read.
7. Do not claim context exists unless Mia returns it.

REST fallback only when MCP tools are not available:

`GET /api/context?folder=<folder>&title=<title>&limit=<n>`

Example:

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_SESSION_TOKEN}" \
  "${MIANOTES_API_URL}/api/context?folder=Mianotes&title=Settings%20Page&limit=5"
```

When the user writes `Mia(workspace: ..., folder: ..., query: ...)`, search that workspace and folder when possible. Use `search_notes` first, then fetch likely full notes with `get_note` before answering.

### Folder Context

When the user writes `Mia(workspace: ..., folder: ...)` in a read/context/search request, treat it as a request to use notes from that folder.

Examples:

- "Before answering, get context from Mia(workspace: Docs, folder: About)."
- "Summarise Mia(workspace: Mianotes, folder: Getting Started)."
- "Use Mia(workspace: My App, folder: Architecture) as context."

Expected behavior:

1. Use MCP tools when available.
2. Pass the workspace name exactly as the user wrote it.
3. Resolve the folder by listing folders in that workspace and matching the folder name case-insensitively.
4. If the user gave a search question or topic, call `search_notes` with the workspace and search terms, then fetch relevant notes with `get_note`.
5. If the user asked for folder-wide context without a search topic, list notes in the resolved folder and fetch the relevant note texts with `get_note`.
6. If the folder is not found, say Mia did not find that folder.
7. Do not read local files or databases unless the user explicitly asks for filesystem recovery/debugging.

### Workspace Context

When the user writes `Mia(workspace: ...)` in a read/context/search request, treat it as a request to use notes from that workspace.

Examples:

- "Before answering, get context from Mia(workspace: Docs)."
- "Search Mia(workspace: Mianotes) for publishing."
- "Summarise what Mia(workspace: My App) knows about architecture."

Expected behavior:

1. Use MCP tools when available.
2. Pass the workspace name exactly as the user wrote it.
3. If the user gave a search question or topic, call `search_notes` with the workspace and search terms, then fetch relevant notes with `get_note`.
4. If the user asked for broad workspace context without a search topic, list folders and notes in that workspace, then fetch only the notes needed to answer.
5. If the workspace is not found or no relevant notes are returned, say that plainly.
6. Do not silently switch to another workspace.

When the user asks to save or document content with `Mia(workspace: ..., folder: ...)`, use the MCP `create_note_in_folder` tool when available. Create a short useful title from the content if the user did not provide one.

## Saving Notes

When the user asks to save content:

1. Resolve the content from the request, previous assistant answer, selected file, link, or nearest relevant conversation context.
2. Resolve the target folder by name.
3. If no folder is clear, use the current folder if obvious; otherwise ask a short clarification.
4. Use a short useful title if the user did not provide one.
5. Save Markdown content.

For MCP, use `create_note`.

For REST, fetch folders with `GET /api/folders`, then create with:

`POST /api/notes/from-text`

REST save flow:

1. Load the REST environment as described in Connection.
2. Fetch folders with `GET /api/folders`.
3. Match the target folder by case-insensitive `name` or `slug`.
4. Create the note with `POST /api/notes/from-text` and the matched `folder_id`.
5. If the target folder does not exist, ask before creating it unless the user explicitly asked to create it.

When saving "your last answer", save the assistant's previous answer, not the user's request.

## Link Commands

When the user asks to save or index a link:

1. Resolve the target folder.
2. Send the URL to Mia.
3. Let Mia fetch, convert, index, and save the page.
4. Return the created note ID, title, status, and API URL when available.

For MCP, use `create_note_from_url`.

For REST, use:

`POST /api/notes/from-url`

## File Commands

When the user asks to save or convert a file, send the file to Mia for conversion and storage. Mia should preserve the source file and save the converted Markdown as a note.

Use the right conversion path based on file type:

- documents, PDFs, spreadsheets, HTML, and text to Markdown
- images to OCR text, then Markdown
- audio to transcript, then Markdown
- links to extracted page Markdown

If the file cannot be converted, explain the failure clearly and do not claim it was saved.

## Prompting Mia

To ask Mia to process an existing note, send a prompt comment beginning with `@mia`.

For MCP, use `add_comment`.

For REST, use:

`POST /api/notes/{note_id}/comments`

```json
{
  "body": "@mia summarise this text"
}
```

Mia prompt responses are synchronous and return Markdown directly. They do not create jobs and do not update the note unless the user explicitly asks to apply, append, or replace the note text.

## Updating Notes

When the user asks to update an existing note:

1. Search Mia for the target note if the note ID is not known.
2. Use the most likely note only when the target is clear from folder, title, and recent context.
3. Ask for clarification when multiple notes could match.
4. Append, replace, rename, publish, or retag only according to the user's wording.

For MCP, use `update_note`.

For REST, use:

`PATCH /api/notes/{note_id}`

Do not overwrite existing notes unless the user explicitly asks to replace them.

## Task Lists

When the user asks for remaining work, next steps, action items, or a to-do list:

1. Create or update a Markdown checklist.
2. Keep tasks specific and actionable.
3. Preserve folder names.
4. Update an existing task note when the user's wording implies continuation.
5. Create a new note when no existing task note is clear.

## Conversation Notes

When the user asks to save a conversation:

1. Extract useful decisions, requirements, commands, and next steps.
2. Avoid saving casual back-and-forth unless the user asks for the full transcript.
3. Prefer a clean Markdown structure with title, summary, decisions, requirements, and next steps.

## Safety Rules

- Do not say Mia saved, indexed, updated, or deleted anything unless the API or MCP call succeeded.
- Do not silently ignore Mia commands.
- Do not save secrets or private credentials unless the user explicitly confirms.
- Do not invent folders, note names, note IDs, or search results.
- Ask for confirmation before destructive actions unless the user clearly requested the exact action.
- When Mia returns context, make clear when an answer is based on Mia.
- Treat Mia as a tool, not hidden memory. Only claim what Mia actually returns.

## Confirmation Style

- Save succeeded: "Saved to Mia under {folder}."
- Link indexed: "Indexed the link in Mia under {folder}."
- Note updated: "Updated the existing note in Mia."
- Search found results: "I found relevant notes in Mia."
- Search found nothing: "I could not find anything relevant in Mia for that search."
- Request failed: "I could not complete that Mianotes request."
