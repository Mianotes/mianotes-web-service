# What is Mianotes?

Mianotes is a local-first knowledge repository for humans and AI agents.

It turns files, links, images, audio, and text into organised Markdown notes. Humans use the web app to read, edit, tag, comment on, and share notes. AI agents use the API or MCP server to create notes, retrieve context, search existing knowledge, update documentation, and leave handoff messages.

## The short version

Mianotes gives agents a place to write down what they are doing as they work.

Instead of losing useful agent output inside chat history, an agent can save decisions, implementation notes, research summaries, source links, and task context into a shared Markdown knowledge base. Humans can then review that knowledge through a local web app.

## Why it exists

AI agents are good at generating useful working notes, but those notes often disappear into temporary chat windows, IDE sidebars, or terminal sessions. Mianotes makes that work durable.

A useful Mianotes note is:

- readable by humans
- stored as Markdown on disk
- indexed in SQLite for fast metadata lookups
- searchable by agents
- linked to source files where possible
- easy to tag, share, and revise

## What Mianotes stores

Mianotes keeps user-facing note content as Markdown files under the active data folder:

```text
data/<folder_slug>/<title_slug>-<note_id>.md
```

The default SQLite database lives inside the hidden runtime folder:

```text
data/.mianotes/mia.db
```

SQLite stores indexes and metadata such as users, folders, tags, notes, comments, sessions, and jobs. The text stays in a Markdown file.

## Humans and agents in the same workspace

Mianotes treats humans and agents as collaborators.

A human might upload a PDF and ask Mia to turn it into a clean note. An agent might create a folder for a task, write implementation notes as it works, attach source material, then update the note when the work changes. Another agent can later search those notes and continue from the same context.

The web app is the human control room. The REST API and MCP server are the agent interface.

## Meet Mia

Mia is the built-in Mianotes agent. Mia helps convert messy input into durable Markdown notes, improve structure, extract useful information, summarise long content, and prepare notes for reuse by humans or other agents.

Read next: [Use cases](02-use-cases.md) or [Installation](../02-getting-started/01-installation.md).
