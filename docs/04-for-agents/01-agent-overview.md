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
```

For narrower automations, create scoped per-user API tokens through `/api/tokens`.

## Service-wide key vs scoped token

| Credential | Best for | Notes |
|---|---|---|
| `MIANOTES_API_KEY` | Trusted local agents and MCP servers | Acts with admin-level access to the current instance. |
| Scoped token | Limited automations | Can grant only the scopes needed, such as `notes:read`. |
| Browser session | Humans in the web app | Do not use browser cookies for agents. |

## API and MCP use the same backend

The MCP server is intentionally thin. It calls the same REST API as other agent clients. It does not bypass the API, read the database directly, or write files directly.

That keeps one permission model for the web app, REST clients, automation scripts, and MCP agents.

Read next: [API tokens](02-api-tokens.md) or [MCP server](03-mcp-server.md).
