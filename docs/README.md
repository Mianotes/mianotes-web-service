# Mianotes documentation

Mianotes is a local-first knowledge repository for humans and AI agents. It turns files, links, images, audio, and plain text into organised Markdown notes that humans can review in a web app and agents can search, update, and maintain through the REST API or MCP.

This documentation is organised for three kinds of reader:

1. **People deciding whether to try Mianotes.** Start with [What is Mianotes?](01-about/01-overview.md), [Use cases](01-about/02-use-cases.md), and [Installation](02-getting-started/01-installation.md).
2. **Humans using the web app.** Start with [Human workflow](03-for-humans/01-human-workflow.md) and [Folders, notes, and tags](03-for-humans/02-folders-notes-tags.md).
3. **People publishing documentation.** Start with [Publishing static sites](03-for-humans/04-publishing.md).
4. **AI agents and developers.** Start with [Agent overview](04-for-agents/01-agent-overview.md), [API tokens](04-for-agents/02-api-tokens.md), [MCP server](04-for-agents/03-mcp-server.md), and [API overview](06-api-reference/01-api-overview.md).

The full table of contents is in [TOC.md](TOC.md).

## Fastest path

Most users should install Mianotes with a package:

- macOS: [Installing from package](02-getting-started/01b-installation-package.md)
- Ubuntu: [Installing from package](02-getting-started/01b-installation-package.md)

Developers and contributors should use [Installing from GitHub](02-getting-started/01a-installation-GitHub.md).

Open the web app, create the first user, then create folders and notes or connect an agent with an API token.

## What Mianotes is best at

- Giving AI agents a durable place to document their work.
- Turning files, URLs, images, audio, and text into Markdown notes.
- Keeping knowledge readable on disk instead of hiding it inside a database blob.
- Letting humans supervise, edit, tag, comment on, and share agent-generated knowledge.
- Publishing selected notes as a static documentation site.
- Supporting local-first workflows with SQLite, Markdown files, and local or OpenAI-compatible LLMs.
