# Agent playbook

This page gives practical patterns for agents using Mianotes.

## Before starting work

1. Search Mianotes for relevant context.
2. Read the most relevant notes fully.
3. Create a new note if the task is new.
4. Add tags that will help future agents find it.

Example search:

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/search?q=api%20token&limit=10"
```

## During work

Update a single task note rather than creating many fragmented notes.

Suggested note structure:

```markdown
# Task: <short task name>

## Goal

What the agent is trying to do.

## Context found

Relevant notes, files, or constraints discovered before starting.

## Decisions

Important choices and why they were made.

## Changes

Files changed, commands run, generated artefacts, or API calls made.

## Tests

Checks run and results.

## Open questions

Anything uncertain or needing human review.

## Handoff

What the next human or agent should do.
```

## After file or URL ingestion

If the agent creates a note from a file or URL, the response will include a `job_api_url`. Poll the job until it succeeds.

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${job_api_url}"
```

Then call the note URL to read the final Markdown.

## Tagging rules

Use tags that are stable and reusable.

Good:

```text
api
security
release
testing
bug
research
```

Avoid:

```text
today
important
thing-i-found
random
```

## What not to store

Agents should not store:

- API keys;
- private keys;
- `.env` contents;
- passwords;
- session cookies;
- confidential files unless the human explicitly wants them in Mianotes.

## Handoff comment

Use comments for review notes or handoff messages.

```json
{
  "body": "Handoff: the API token docs are updated. Please review the security section before release."
}
```

Use `@mia` only when the agent wants Mia to process the current note privately.
