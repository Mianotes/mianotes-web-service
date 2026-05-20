---
name: mianotes
description: Use when the user says Mia or Mianotes, asks to save, search, retrieve, update, prompt, index links, convert files, or use local folder knowledge before answering.
---

# Mianotes

Mia is the local Mianotes knowledge service. Use Mia as the user's local project memory for Markdown notes, files, links, folders, and reusable context.

Prefer Mianotes MCP tools when available. If MCP tools are not available, use the REST API.

## Connection

- Default API URL: `http://127.0.0.1:8200`
- Override with `MIANOTES_API_URL`
- Authenticate with `MIANOTES_API_TOKEN`
- Never write tokens, API keys, passwords, or private credentials into notes, docs, commits, logs, or examples that will be saved.

## Available MCP Tools

Use the real Mianotes MCP tool names when available:

- `list_folders`
- `create_folder`
- `list_notes`
- `get_note`
- `create_note`
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
