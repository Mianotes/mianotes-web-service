# Configuration options

Mianotes configuration uses environment variables with the `MIANOTES_` prefix.

For normal local use, configure only the LLM provider and API key. Leave storage settings at their defaults unless you need a custom layout.

## Common variables

| Variable | Default | Description |
|---|---|---|
| `MIANOTES_HOST` | `0.0.0.0` or script default | Host interface for the web service. Use `127.0.0.1` for local-only use. |
| `MIANOTES_PORT` | `8200` | Web service port. |
| `MIANOTES_DATA_DIR` | `data` | Folder where Markdown notes, source files, and the hidden `.mianotes/` runtime folder live. |
| `MIANOTES_DATABASE_URL` | empty | Optional explicit database URL. Leave empty for normal SQLite setup. |
| `MIANOTES_LLM_PROVIDER` | `openai` | LLM provider: `openai`, `local`, or `openai-compatible`. |
| `MIANOTES_LLM_MODEL` | `gpt-4o-mini` | Text model used by Mia. |
| `MIANOTES_LLM_BASE_URL` | empty | Base URL for local or OpenAI-compatible providers. |
| `MIANOTES_LLM_API_KEY` | empty | LLM provider API key or local placeholder. |
| `MIANOTES_LLM_IMAGE_MODEL` | empty | Optional multimodal OpenAI model for image OCR fallback. |
| `MIANOTES_API_KEY` | empty | Service-wide bearer token used by local agents and MCP. |

## Ports

Mianotes services use the `8200` range:

```text
8200  web service
8201  alternate local service
```

To start on another port during development:

```bash
MIANOTES_HOST=127.0.0.1 MIANOTES_PORT=8201 ./start-dev.sh
```

## Storage defaults

Generated notes and source files live under the configured data directory:

```text
data/<folder_slug>/<title_slug>-<note_id[:8]>.md
data/<folder_slug>/sources/<note_id[:8]>/original.<ext>
```

Folder directories are filesystem-safe slugs and are unique inside a workspace. Source files live under each folder's `sources/` directory.

## Database defaults

When `MIANOTES_DATABASE_URL` is empty, Mianotes uses SQLite at:

```text
data/.mianotes/mia.db
```

Most installs should leave `MIANOTES_DATABASE_URL` empty.

To force an absolute SQLite database path:

```env
MIANOTES_DATABASE_URL=sqlite:////absolute/path/to/.mianotes/mia.db
```

To point the service at a specific data folder:

```env
MIANOTES_DATA_DIR=/absolute/path/to/mianotes-data
```

## LLM provider values

### OpenAI

```env
MIANOTES_LLM_PROVIDER=openai
MIANOTES_LLM_MODEL=gpt-4o-mini
MIANOTES_LLM_API_KEY=sk-...
```

### Local Ollama-style provider

```env
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2:3b
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
MIANOTES_LLM_API_KEY=ollama
```

### Other OpenAI-compatible endpoint

```env
MIANOTES_LLM_PROVIDER=openai-compatible
MIANOTES_LLM_MODEL=<model-name>
MIANOTES_LLM_BASE_URL=<base-url>
MIANOTES_LLM_API_KEY=<token-or-local-placeholder>
```

## Agent access variables

The service-wide key is for trusted local agents and MCP servers:

```env
MIANOTES_API_URL=http://127.0.0.1:8200
MIANOTES_API_KEY=mia_or_long_service_secret
```

Agent clients send it as:

```http
Authorization: Bearer <token>
```

Scoped per-user API tokens are available through `/api/tokens` when an automation needs narrower permissions.

Read next: [Ollama, OpenAI, and local models](04-ollama-openai.md).
