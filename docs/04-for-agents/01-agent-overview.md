# Agent overview

Mianotes is designed for collaboration between humans and AI agents.

AI agents write plans, explain changes, debug issues, summarise research, and leave useful context behind. But most of that work disappears inside temporary chats, IDE sidebars, Slack threads, and terminal sessions. Mianotes gives that work a place to live. Agents can save decisions, implementation notes, summaries, source links, files, images, and project context into clean Markdown notes, so the next agent can pick up the same context without asking you to explain everything again.

Agents should use Mianotes as a local documentation layer. They can save useful context while they work, then retrieve that context later through search, API calls, or MCP tools.

## What agents can do

An agent can:

- create folders for tasks, experiments, projects, or research threads;
- add notes from text;
- create notes from URLs;
- upload files through the REST API;
- read notes;
- update notes;
- set tags;
- search Markdown notes;
- leave comments or handoff messages;
- send private `@mia` prompts through the comments endpoint.

## Recommended agent behaviour

Agents should document durable information, not every temporary thought.

Good agent notes include:

- decisions made;
- relevant commands run;
- files changed;
- why an implementation changed;
- bugs found and fixed;
- test results;
- next steps;
- links to source material;
- warnings about uncertainty.

Avoid filling Mianotes with low-value logs that no human or agent will reuse.

## Access model

Agents should use API tokens or MCP tools, not browser cookies.

The simplest trusted local setup uses the service-wide key:

```env
MIANOTES_API_URL=http://127.0.0.1:8200
MIANOTES_API_KEY=<create_api_key_in_settings>
MIANOTES_CLIENT_NAME=Codex
```

For narrower automations, create scoped per-user API tokens through `/api/tokens`.

Agents should exchange the API key and client name for a short-lived agent
session before making API calls. The session identifies the tool, such as
`Codex`, `Claude`, `Cursor`, or `Slack`, without embedding the raw API key.
Mianotes maps known client names to stable client IDs for Console attribution.
Unknown client names are treated as `MCP`.

## Service-wide key vs scoped token

| Credential | Best for | Notes |
|---|---|---|
| `MIANOTES_API_KEY` | Trusted local agents and MCP servers | Acts with admin-level access across configured workspaces. |
| Scoped token | Limited automations | Can grant only the scopes needed, such as `notes:read`. |
| Browser session | Humans in the web app | Do not use browser cookies for agents. |

## API and MCP use the same backend

The MCP server is intentionally thin. It calls the same REST API as other agent clients. It does not bypass the API, read the database directly, or write files directly.

That keeps one permission model for the web app, REST clients, automation scripts, and MCP agents.

## Workspace targeting

Mianotes can manage multiple workspaces. Agents should target the requested workspace explicitly instead of assuming the active browser workspace.

MCP tools accept a `workspace` argument for workspace-content calls. REST clients should send:

```http
X-Mianotes-Workspace: <workspace-id>
```

Use these shorthand forms in prompts and agent instructions:

- `Mia(<workspace>: <search_query>)` searches a workspace.
- `Mia(<workspace>/<folder>: <search_query>)` searches a folder inside a workspace.
- `Mia(<workspace>/<folder>)` saves content into that workspace and folder.

When saving with `Mia(<workspace>/<folder>)`, create a useful title from the content if the user did not provide one.

Read next: [API tokens](02-api-tokens.md) or [MCP server](03-mcp-server.md).
