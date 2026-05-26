# First run

The first run creates the first user, the master password, the default storage folder, and the first notes folder.

## What happens on first setup

When no Mianotes instance has been configured yet, the first user joins through:

```text
POST /api/auth/join
```

Mianotes then:

1. creates the first admin user;
2. stores the master password hash;
3. initialises `data/.mianotes/mia.db`;
4. seeds the default `Mianotes` folder;
5. starts a browser session for the new user.

The first user is the admin for that folder.

## Recommended first-run flow

The frontend can call:

```text
POST /api/auth/check-email
```

When the response contains:

```json
{
  "user_id": null,
  "is_first_user": true
}
```

show a setup screen that explains that the first password becomes the master password for this Mianotes instance.

## First folder

After setup, create a folder for the work you want Mianotes to remember.

Good starter folders:

- `Mianotes`
- `Research`
- `Project notes`
- `Agent worklog`
- `School`
- `Receipts`
- `Family notes`

## First note

Start with a simple text note before uploading files.

Example note:

```markdown
# First Mianotes note

This is a test note. It should be stored as Markdown, listed in the web app, and searchable through the API.
```

Then search for it:

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/search?q=test"
```

## First file upload

After text notes work, try a small file such as a `.txt`, `.md`, `.pdf`, `.jpg`, or `.png`.

File and URL ingestion return a pending note plus a job. The conversion runs in the background. Clients should poll the job URL until the job reaches `succeeded`, then fetch the note.

## First agent connection

Create or configure an API key, then test the session endpoint:

```bash
export MIANOTES_API_URL="http://127.0.0.1:8200"
export MIANOTES_API_KEY="mia_or_service_key_here"

curl -sS \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL}/api/auth/session"
```

Read next: [API tokens](../04-for-agents/02-api-tokens.md).
