# MCP

Mianotes ships a stdio MCP server for compatible AI agents. The MCP server calls
the same REST API as other agent clients, so normal token scopes and backend
permission checks still apply.

## Running the MCP server

Set the API URL and an agent token, then start the server:

```bash
MIANOTES_API_URL=http://127.0.0.1:8200 \
MIANOTES_API_TOKEN=mia_your_token \
python -m mianotes_web_service.mcp_server
```

Fresh package installs also expose the `mianotes-mcp` console script:

```bash
MIANOTES_API_URL=http://127.0.0.1:8200 \
MIANOTES_API_TOKEN=mia_your_token \
mianotes-mcp
```

## Authentication

MCP clients should use scoped API tokens, not browser cookies. Create tokens
through the REST API or web app, then pass the raw token as `MIANOTES_API_TOKEN`.

The token should include only the scopes the agent needs. Use `admin` only for
trusted local automation.

## Tools

The current MCP surface includes tools for:

- Listing projects
- Creating projects
- Listing notes
- Reading notes
- Creating notes from text
- Creating notes from URLs
- Updating notes
- Adding comments
- Setting tags
- Searching Markdown notes
- Creating Mia summarise jobs
- Creating Mia structure jobs
- Creating Mia extract jobs
- Creating Mia rewrite jobs

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
