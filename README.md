# Mianotes Web Service

[![CI](https://github.com/Mianotes/mianotes-web-service/actions/workflows/ci.yml/badge.svg)](https://github.com/Mianotes/mianotes-web-service/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/framework-FastAPI-009688?logo=fastapi&logoColor=white)
![Parser](https://img.shields.io/badge/parser-MarkItDown-2563EB)
![MCP](https://img.shields.io/badge/MCP-enabled-7C3AED)
![Code style](https://img.shields.io/badge/code%20style-Ruff-D7FF64?logo=ruff&logoColor=111111)

The Python backend for Mianotes, providing the local REST API, filesystem-backed Markdown storage, SQLite indexing, file/link parsing, agent tokens, MCP tools, and Mia prompt integration.

The service is designed for small groups: developers, researchers, students, and families who want durable knowledge stored as plain files that people, agents, and tools like OpenClaw, Claude, Codex, Copilot, Gemini, and Slack can use directly. It uses the filesystem as its main storage layer, which makes it extremely portable and easy to run locally on your computer or on a hosted server without relying on an external database server.

## What it does

- Stores note text as Markdown on the filesystem.
- Keeps users, folders, notes, tags, comments, jobs, sessions, and API tokens indexed in SQLite.
- Converts uploaded files and URLs through a MarkItDown-based parser layer.
- Supports browser sessions, one service-wide API key for local agents, and scoped per-user tokens for narrower automations.
- Exposes JSON REST APIs for the web app and external automation.
- Provides a stdio MCP server so compatible AI agents can use Mianotes as a local knowledge tool.
- Supports local LLMs, or OpenAI, for Mia prompts sent through comments.

## Documentation

This documentation is organised for three kinds of reader:

1. **People deciding whether to try Mianotes.** Start with [What is Mianotes?](docs/01-about/01-overview.md), [Use cases](docs/01-about/02-use-cases.md), and [Installation](docs/02-getting-started/01-installation.md).
2. **Humans using the web app.** Start with [Human workflow](docs/03-for-humans/01-human-workflow.md) and [Folders, notes, and tags](docs/03-for-humans/02-folders-notes-tags.md).
3. **People publishing documentation.** Start with [Publishing static sites](docs/03-for-humans/04-publishing.md).
4. **AI agents and developers.** Start with [Agent overview](docs/04-for-agents/01-agent-overview.md), [API tokens](docs/04-for-agents/02-api-tokens.md), [MCP server](docs/04-for-agents/03-mcp-server.md), and [API overview](docs/06-api-reference/01-api-overview.md).

The full table of contents is in [TOC.md](docs/TOC.md).

## Technology

- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- SQLite
- MarkItDown
- Trafilatura
- Local LLMs, or OpenAI
- pytest
- Ruff

## License

Mianotes Web Service is licensed under GPL-3.0. See [LICENCE](LICENCE).
