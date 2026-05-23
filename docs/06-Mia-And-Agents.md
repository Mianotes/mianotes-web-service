# Mia and agents

Mianotes is designed for collaboration between humans and AI agents.

## The problem

AI agents often rely on remote models to extract, structure, and summarise information from files. Local models can help summarise text, but they do not solve the whole workflow: parsing files, organising outputs, maintaining durable notes, improving structure over time, and making that information available to other agents.

Mianotes fills that gap by providing a local-first knowledge repository that agents can connect to through APIs and, later, MCP.

## Mia

Mia is the built-in Mianotes agent. Mia helps users and other agents:

- Convert documents, images, links, text, and audio into Markdown notes.
- Extract key information from source material.
- Improve note structure.
- Summarise long notes.
- Rewrite notes for clarity.
- Maintain tags and metadata.

Mia should be implemented as a backend service/agent layer, not as frontend-only behaviour. The web app can prompt Mia, but the backend owns the workflow, permissions, and persistence.

## Human users

Humans use Mianotes through the web app. They can:

- Browse the shared knowledge base.
- Add folders and notes.
- Upload files.
- Prompt Mia from comments.
- Comment, tag, share, and export information.

## Agent users

AI agents use Mianotes programmatically. They can:

- Create folders for tasks or folders.
- Add notes as they work.
- Attach source files.
- Update notes when new information appears.
- Use tags to organise memory.
- Query notes through search.
- Prompt Mia from comments.

Agents should use API tokens and MCP tools, not browser cookies. The default
setup uses the service-wide `MIANOTES_API_KEY` from the web service `.env`.
That private token works across database switches because each `mia.db` stores
only the token's derived public hash.

The stdio MCP server is started with `MIANOTES_API_URL` and
`MIANOTES_API_KEY`, then calls the same REST API as any other agent client. If
the MCP process is started outside the web service shell, source the same `.env`
first so you do not duplicate the token in multiple places.

## Design principle

The backend is the brain. The web app explains context and collects input, but the web service decides permissions, ownership, roles, parsing behaviour, share access, and agent capabilities.

## MCP surface

The MCP server lets compatible agents use Mianotes as a toolset. See
[MCP](07-MCP.md) for setup, authentication, and the current tool list.

Mia supports OpenAI and local OpenAI-compatible LLMs through the same provider
boundary. This lets a Mianotes instance run Mia against OpenAI, a local
Ollama-style server, or another compatible endpoint without changing the REST
or MCP API.

In v1, Mia is prompted through the comments endpoint. When the request body
starts with `@mia`, the backend treats it as a private prompt, sends the prompt
and note Markdown to the configured LLM provider, and returns Markdown directly.
This does not create a job, does not save a shared comment, and does not update
the note. See [Comments](11-Comments.md) for the exact request and response
shape.
