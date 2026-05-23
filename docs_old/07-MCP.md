# MCP

Mianotes ships a stdio MCP server for compatible AI agents. The MCP server calls
the same REST API as other agent clients, so normal token scopes and backend
permission checks still apply.

## Running the MCP server

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

The MCP process needs `MIANOTES_API_KEY` in its environment. The simplest way
is to source the same `.env` file used by the web service. Do not copy the token
into extra files unless you have to.

## Authentication

By default, MCP clients use the service-wide `MIANOTES_API_KEY`. The raw key
stays in `.env`; each `mia.db` stores only a derived public hash. The token acts
as the first admin user in the selected database, after that database has been
set up.

`MIANOTES_API_TOKEN` is still accepted as a backwards-compatible alias.

Scoped per-user API tokens are still available for narrower automations. Use
scoped tokens when an agent should only read notes or work in a limited role.

## Tools

The current MCP surface includes tools for:

- Listing folders
- Creating folders
- Listing notes
- Reading notes
- Creating notes from text
- Creating notes from URLs
- Updating notes
- Sending private synchronous `@mia` prompts through the comments endpoint
- Setting tags
- Searching Markdown notes

## Ingestion results

`create_note_from_url` returns the same ingestion response as the REST API. It
does not wait for the page to be converted before returning. The response
includes:

- `note_id`
- `job_id`
- `job_status`
- `note_api_url`
- `job_api_url`
- The nested note object
- The nested job object

Agents should poll `job_api_url` until the job reaches `succeeded`, then call
`get_note` with `note_id` to retrieve the finished Markdown content.

The MCP server does not currently expose binary file upload. File ingestion is
available through `POST /api/notes/from-file`; an MCP file-ingestion tool can be
added later if agent clients need to pass local files through the MCP surface.

## Design notes

The MCP server is intentionally thin. It does not bypass the API, read the
database directly, or write files directly. That keeps one permission model for
the web app, REST clients, automation scripts, and MCP agents.
