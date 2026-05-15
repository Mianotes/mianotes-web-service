# Introduction

Mianotes is a local-first knowledge repository for humans and AI agents. It turns files, links, images, audio, and text into organised Markdown notes that agents can query, improve, and maintain through APIs and MCP, while humans collaborate through a web app.

The core idea is simple: Markdown files are the shared working memory. Humans can read and edit them through the web app. AI agents can create, update, tag, search, and maintain them programmatically.

Mia is the built-in AI agent for Mianotes. Mia helps convert messy inputs into durable notes, then improves those notes by structuring them, extracting key information, summarising content, and preparing them for reuse by humans or other agents.

## Use Cases

- Give AI agents a local, structured place to maintain their own documentation.
- Save meeting notes, homework, receipts, trip plans, research, and reference documents.
- Upload files and keep their original source next to the generated Markdown note.
- Ask Mia to improve, summarise, extract, or restructure notes.
- Browse notes by person, topic, tag, or recency.
- Share a read-only note link with someone outside the household or team.
- Keep content transparent on disk instead of hiding it in a database blob.

## Storage Model

Mianotes stores note content as Markdown files:

```text
data/<username>/<topic>/<note_id>.md
```

SQLite stores the index and metadata: users, topics, tags, notes, comments, source files, sessions, and share tokens.

The filename is the note ID, not the note title. This keeps paths stable when titles change and makes future filesystem search simple to join back to note metadata.

## Humans And Agents

Mianotes treats humans and AI agents as collaborators in the same workspace. A human might upload a PDF and ask Mia to turn it into a clear project note. An agent might connect through the API, create a topic for a task, add notes as it works, and later update those notes with findings.

The web app is the human control room. The API and future MCP server are the agent interface.
