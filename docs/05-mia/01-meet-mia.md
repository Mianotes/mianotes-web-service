# Meet Mia

Mia is the built-in AI agent for Mianotes.

Mia helps humans and other agents turn messy input into reusable Markdown notes.

## What Mia does

Mia can help with:

- converting documents, images, links, text, and audio into Markdown notes;
- extracting key information from source material;
- improving note structure;
- summarising long notes;
- rewriting notes for clarity;
- preparing knowledge for reuse by humans or agents.

## Mia belongs in the backend

Mia runs as a backend service and agent layer, not frontend-only behaviour.

The web app can collect prompts and show results, but the backend owns:

- permissions;
- ownership;
- parsing behaviour;
- persistence;
- LLM provider calls;
- job state;
- share access;
- agent capabilities.

This keeps browser users, REST clients, automation scripts, and MCP agents under one capability model.

## Provider boundary

Mia calls models through a provider boundary.

Supported provider values:

```text
openai
local
openai-compatible
```

Local mode uses the same OpenAI client shape against an OpenAI-compatible endpoint, which makes Ollama-style tools fit the same code path.

## Mia and jobs

File and URL ingestion use background jobs. Mia prompts through comments are synchronous and do not create jobs.

Use jobs for conversion work that may take time. Use `@mia` prompts for immediate analysis of an existing note.

Read next: [Prompting Mia](02-prompting-mia.md).
