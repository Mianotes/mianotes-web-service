# Troubleshooting

Use this page when setup or ingestion does not behave as expected.

## Service is not reachable

Check health:

```bash
curl -i http://127.0.0.1:8200/api/health
```

If the service is running on another port, set `MIANOTES_API_URL`:

```bash
export MIANOTES_API_URL="http://127.0.0.1:8201"
```

## `401 Not authenticated`

The request is missing a valid browser session or bearer token.

For API clients:

```bash
curl -i \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/auth/session"
```

Make sure the token is in the environment used by the shell, agent, or MCP process.

## `403 Permission denied`

The token was accepted, but it does not have the scope required for that endpoint.

Use a service-wide key for trusted local agents, or create a scoped token with the right scopes:

```text
notes:read
notes:write
folders:read
folders:write
comments:write
tags:read
tags:write
share:write
tokens:read
tokens:write
admin
```

## Search returns `503`

Mianotes searches Markdown files with `ripgrep`. Install it and restart the service.

macOS:

```bash
brew install ripgrep
```

Linux:

```bash
sudo apt install ripgrep
```

## Image OCR fails on Apple Silicon

Run:

```bash
tesseract --version
```

If you see `Bad CPU type in executable`, reinstall Tesseract with ARM Homebrew:

```bash
brew reinstall tesseract
```

Restart Mianotes after reinstalling.

## File or URL note stays pending

File and URL ingestion create a background job. Poll the job URL returned in the creation response:

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL}/api/jobs/<job_id>"
```

When the job reaches `succeeded`, fetch the note from `note_api_url`.

## Mia returns `503`

Mia is not configured or the configured LLM provider is unavailable.

Check:

- `MIANOTES_LLM_PROVIDER`
- `MIANOTES_LLM_MODEL`
- `MIANOTES_LLM_BASE_URL`
- `MIANOTES_LLM_API_KEY`
- whether Ollama or the chosen local endpoint is running

## MCP cannot authenticate

The MCP process needs access to the same API URL and token as other agent clients:

```bash
export MIANOTES_API_URL="http://127.0.0.1:8200"
export MIANOTES_API_KEY="mia_or_service_key_here"
mianotes-mcp
```

If your MCP client starts the server from a different shell, make sure that shell can see the same environment variables.
