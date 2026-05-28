# Maintainer checklist

Use this checklist before publishing a new Mianotes release or updating the documentation.

## Documentation structure

- Root `TOC.md` exists.
- Quick-start information is near the top of the docs.
- Agent docs are separated from human workflow docs.
- API reference is grouped by task, not dumped as one long page.
- Security warnings are explicit and easy to find.
- Configuration examples use `MIANOTES_` variables consistently.
- Local-first positioning is clear but not overstated.

## Release checks

Run:

```bash
python -m compileall -q src tests
pytest
ruff check .
```

## Manual smoke checks

- Fresh install starts with `./start.sh`.
- First user setup works.
- Text note creation works.
- File upload creates a job and eventually updates the note.
- URL ingestion creates a job and eventually updates the note.
- Search returns note metadata and excerpts.
- `@mia` prompt returns a prompt response and does not save a comment.
- API key creation returns the raw key once.
- Scoped token permissions produce expected `401` and `403` behaviour.
- MCP server starts with `MIANOTES_API_URL` and `MIANOTES_API_KEY`.
- Share link can be created, loaded without auth, and revoked.
- Publish draft navigation includes all publishable notes for the selected scope.
- Publish draft **New notes** only lists paths that were not in the previous publish.
- Static sites render code blocks, tables, admonitions, search, and **On this page**.
- `mialight` and `miadark` both render readable article pages.
- Published site preview and ZIP download both work.

## Security checks

- `.env` is not committed.
- `workspaces.json` is not committed.
- `data/`, `.mianotes/`, and `mia.db` are not committed.
- Example tokens are fake.
- Docs remind users not to give untrusted agents filesystem access to sensitive files.
- File API blocks database files.
- Hosted deployment docs mention firewall and HTTPS.

## Documentation update checklist

When an endpoint changes:

1. Update the relevant API reference page.
2. Update agent docs if the endpoint is useful to agents.
3. Update security docs if auth or scope behaviour changed.
4. Add or update examples.
5. Run a link check across Markdown files.

When the UI changes:

1. Update human workflow docs.
2. Update first-run docs if setup changed.
3. Update theming/customisation docs if visual configuration changed.
4. Keep screenshots optional so docs do not break when images are missing.
