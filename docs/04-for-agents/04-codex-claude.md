# Codex, Claude, Cursor, and other agents

Mianotes is intended to be useful for Codex, Claude Code, OpenClaw, Cursor, VS Code agents, Slack bots, and local automation.

The core idea is the same for every tool: give the agent a safe API or MCP connection, then ask it to write durable notes as it works.

## Installed skills

The Mianotes setup scripts install local Mianotes skill files for Codex and Claude:

```text
~/.codex/skills/mianotes/SKILL.md
~/.claude/skills/mianotes/SKILL.md
```

The development installer also copies the repository skill to those locations.

These skill files should explain how the agent can use Mianotes during a coding or research session.

## Environment for agents

Agents need access to the API URL and token:

```env
MIANOTES_API_URL=http://127.0.0.1:8200
MIANOTES_API_KEY=mia_or_service_key_here
MIANOTES_CLIENT_NAME=Codex
```

If the agent starts from a different shell than the web service, make sure the agent environment contains these variables.

## MCP-capable agents

For MCP-capable clients, configure the client to start:

```bash
mianotes-mcp
```

or:

```bash
python -m mianotes_web_service.mcp_server
```

The MCP server reads `MIANOTES_API_URL`, `MIANOTES_API_KEY`, and
`MIANOTES_CLIENT_NAME`. It exchanges the API key for a short-lived agent session,
then calls the REST API with that session token.

## REST-capable agents

Any agent that can make HTTP requests can use the REST API directly.

Minimal search example:

```bash
MIANOTES_SESSION_TOKEN="$(
  curl -sS -X POST \
    -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
    -H "X-Mianotes-Client: ${MIANOTES_CLIENT_NAME:-Codex}" \
    "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/auth/agent-session" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["token"])'
)"

curl -sS \
  -H "Authorization: Bearer ${MIANOTES_SESSION_TOKEN}" \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/search?q=settings"
```

Minimal note creation example:

```bash
curl -sS \
  -X POST \
  -H "Authorization: Bearer ${MIANOTES_SESSION_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "folder_id": "<folder-id>",
    "title": "Agent worklog",
    "text": "# Agent worklog\n\nThe agent started documenting this task."
  }' \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/notes/from-text"
```

## Recommended prompt for coding agents

```text
Use Mianotes as the durable project memory. Before making changes, search Mianotes for relevant project notes. While working, create or update a note with the goal, decisions, files changed, tests run, and next steps. Do not store secrets. Keep notes concise and useful for the next developer or agent.
```

## Safety rule

Treat any agent with a valid Mianotes token as trusted. Mianotes can authenticate and audit the caller, but it cannot sandbox an agent that already has filesystem access to sensitive local files.

Read next: [Security](../07-system/03-security.md).
