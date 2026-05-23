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

- [Introduction](docs/01-Introduction.md)
- [Installation](docs/02-Installation.md)
- [Workflow](docs/03-Workflow.md)
- [APIs](docs/04-API.md)
- [Customisation](docs/05-Customisation.md)
- [Database](docs/13-Database.md)
- [Mia and agents](docs/06-Mia-And-Agents.md)
- [MCP](docs/07-MCP.md)
- [Architecture](docs/08-Architecture.md)
- [Development](docs/09-Development.md)
- [Testing](docs/10-Testing.md)
- [Comments](docs/11-Comments.md)
- [Security](docs/12-Security.md)

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
