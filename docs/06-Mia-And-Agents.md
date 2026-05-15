# Mia And Agents

Mianotes is designed for collaboration between humans and AI agents.

## The Problem

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

## Human Users

Humans use Mianotes through the web app. They can:

- Browse the shared knowledge base.
- Add topics and notes.
- Upload files.
- Ask Mia to improve notes.
- Comment, tag, share, and export information.

## Agent Users

AI agents use Mianotes programmatically. They can:

- Create topics for tasks or projects.
- Add notes as they work.
- Attach source files.
- Update notes when new information appears.
- Use tags to organise memory.
- Query notes through search.
- Ask Mia to improve or extract content.

Agents should use scoped API tokens and MCP tools, not browser cookies.

## Design Principle

The backend is the brain. The web app explains context and collects input, but the web service decides permissions, ownership, roles, parsing behaviour, share access, and agent capabilities.

## Future MCP Surface

The MCP server should let compatible agents use Mianotes as a toolset:

- Search notes
- Read note
- Create note
- Update note
- Add source file
- Add comment
- Set tags
- Create topic
- Ask Mia to summarise, structure, extract, or rewrite
