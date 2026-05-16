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

- Listing topics
- Creating topics
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

## Design notes

The MCP server is intentionally thin. It does not bypass the API, read the
database directly, or write files directly. That keeps one permission model for
the web app, REST clients, automation scripts, and MCP agents.
