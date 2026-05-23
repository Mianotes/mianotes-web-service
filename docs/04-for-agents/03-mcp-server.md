# MCP server

Mianotes ships a stdio MCP server for compatible AI agents.

The MCP server calls the same REST API as other agent clients, so normal token scopes and backend permission checks still apply.

## Run the MCP server

Load the service `.env`, set the API URL if needed, then start the server:

```bash
set -a
. ./.env
set +a
MIANOTES_API_URL=${MIANOTES_API_URL:-http://127.0.0.1:8200} \
python -m mianotes_web_service.mcp_server
```

Fresh package installs also expose the `mianotes-mcp` console script:

```bash
set -a
. ./.env
set +a
MIANOTES_API_URL=${MIANOTES_API_URL:-http://127.0.0.1:8200} \
mianotes-mcp
```

The MCP process needs `MIANOTES_API_KEY` in its environment.

## Authentication

By default, MCP clients use the service-wide `MIANOTES_API_KEY`.

```env
MIANOTES_API_URL=http://127.0.0.1:8200
MIANOTES_API_KEY=mia_or_service_key_here
```

`MIANOTES_API_TOKEN` is still accepted as a backwards-compatible alias.

Use scoped per-user API tokens when an agent should only read notes or work in a limited role.

## Current MCP tools

The current MCP surface includes tools for:

- listing folders;
- creating folders;
- listing notes;
- reading notes;
- creating notes from text;
- creating notes from URLs;
- updating notes;
- sending private synchronous `@mia` prompts through the comments endpoint;
- setting tags;
- searching Markdown notes.

## URL ingestion results

`create_note_from_url` returns the same ingestion response as the REST API. It does not wait for the page to be converted before returning.

The response includes:

- `note_id`;
- `job_id`;
- `job_status`;
- `note_api_url`;
- `job_api_url`;
- the nested note object;
- the nested job object.

Agents should poll `job_api_url` until the job reaches `succeeded`, then call `get_note` with `note_id` to retrieve the finished Markdown content.

## File ingestion

The MCP server does not currently expose binary file upload. File ingestion is available through:

```text
POST /api/notes/from-file
```

An MCP file-ingestion tool can be added later if agent clients need to pass local files through the MCP surface.

## Design rule

The MCP server should stay thin. It should not read `mia.db`, bypass REST permissions, or write files directly. The API remains the single authority for permissions, parsing, job state, and persistence.
