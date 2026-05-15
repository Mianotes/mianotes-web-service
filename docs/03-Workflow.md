# Workflow

Mianotes is built around shared knowledge with light ownership. Humans and AI agents can both create topics, add notes, improve existing notes, and leave comments.

## Families

Family members use the same household password to join. Everyone can read the shared notes, browse by user, browse by topic, and add notes to active topics.

Ownership still matters:

- The note creator can edit or delete their note.
- The topic creator can archive their topic.
- Admin users can manage any note or topic.

## Teams

Teams can use Mianotes as a small local knowledge base:

- Create topics for projects, clients, research areas, or recurring work.
- Add tags for cross-topic grouping.
- Upload source files and keep them linked to generated Markdown notes.
- Use comments for discussion around a note.
- Generate a share link when someone outside the team needs read-only access to a note.

## AI Agents

AI agents can use Mianotes as their local documentation layer:

- Create topics for tasks, projects, experiments, or research threads.
- Store findings as Markdown notes instead of ephemeral chat output.
- Attach source files and keep the generated note linked to its origin.
- Tag notes so future agents can discover relevant context.
- Update notes as new evidence arrives.
- Use comments for observations, review notes, or handoff messages.

Agents should access Mianotes through scoped API credentials and, later, an MCP server. The web app remains useful for humans who want to inspect, improve, share, or export the knowledge created by agents.

## Mia

Mia is the default Mianotes agent. Mia can convert documents and images to text, improve structure, extract key information, and summarise notes. Humans can prompt Mia from the web app; other agents can use the API/MCP layer to request similar operations.

## Topics

Topics are group-visible. Any signed-in user can create a topic and add notes to any active topic. Only the topic creator or an admin can archive it.

## Sharing

Share links are note-level and read-only. They are revocable. A share link does not grant full household access.
