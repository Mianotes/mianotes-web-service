# API token

Mianotes API clients authenticate with bearer tokens. A token lets an agent,
script, MCP server, or other tool call the same local REST API that the web app
uses.

The easiest way to get started is through the web app. Sign in as an admin,
open **Settings**, and use **Create API Key**. Mianotes shows the key once. Copy
it immediately and put it in the environment of the agent, app, or tool that
needs to connect.

```env
MIANOTES_API_URL=http://127.0.0.1:8200
MIANOTES_API_KEY=mia_paste_the_key_here
```

Use that value as a bearer token:

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL}/api/auth/session"
```

## How Mianotes stores the key

The raw key is a secret. Treat it like a password.

Mianotes compares bearer tokens by hashing the presented token and comparing it
with the public verifier stored in the active `.mianotes/mia.db`. The database does not
store the raw key.

There are two normal places the raw service key can live:

- if you set `MIANOTES_API_KEY` in the web service environment, the raw secret
  lives in that environment;
- if you create the key from the Settings screen or `POST /api/settings/api-key`,
  Mianotes writes the raw service key to the local `storage.json` file so it can
  survive service restarts.

`storage.json` is a private runtime file and is ignored by Git. Keep it private.

On startup and on authenticated requests, Mianotes syncs the derived public
verifier into the active database. This lets the same service key work after a
restart and across folder switches, while each `.mianotes/mia.db` still stores
only the public verifier.

## Get a key in the web app

This is the recommended path for most people because it avoids hand-writing API
requests.

1. Start the Mianotes web service.
2. Open the Mianotes web app.
3. Sign in as an admin user.
4. Open **Settings**.
5. Find **Create API Key**.
6. Click **Create API Key**.
7. Copy the key immediately.
8. Add it to the environment used by your agent, app, MCP server, or shell.

For a local shell:

```bash
export MIANOTES_API_URL="http://127.0.0.1:8200"
export MIANOTES_API_KEY="mia_paste_the_key_here"
```

For a project `.env` file:

```env
MIANOTES_API_URL=http://127.0.0.1:8200
MIANOTES_API_KEY=mia_paste_the_key_here
```

Then test it:

```bash
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL}/api/auth/session"
```

## Get a key from the API

You can also create the service API key directly from the REST API. Use this
when you are setting up Mianotes from a script or when the web app is not
available.

You must call this endpoint as an admin. The simplest way is to sign in through
the browser first, then send the request with the browser session cookie.

If you are scripting the whole flow, first resolve the admin user's ID:

```bash
curl -sS \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com"}' \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/auth/check-email"
```

Then sign in and save the session cookie:

```bash
curl -sS \
  -X POST \
  -c cookies.txt \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "paste-user-id-from-check-email",
    "password": "your-admin-password"
  }' \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/auth/login"
```

Then create the service API key with that saved cookie:

```bash
curl -sS \
  -X POST \
  -b cookies.txt \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/settings/api-key"
```

The response contains the raw key once:

```json
{
  "token": "mia_generated_key_returned_once"
}
```

Save it somewhere private, then use it as `MIANOTES_API_KEY` for clients:

```bash
export MIANOTES_API_KEY="mia_generated_key_returned_once"
curl -sS \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/folders"
```

If you already have an admin bearer token, you can create a new service API key
without a browser cookie:

```bash
curl -sS \
  -X POST \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/settings/api-key"
```

## Use the token from JavaScript

```js
const apiUrl = process.env.MIANOTES_API_URL ?? "http://127.0.0.1:8200";
const apiKey = process.env.MIANOTES_API_KEY;

const response = await fetch(`${apiUrl}/api/search?q=settings`, {
  headers: {
    Authorization: `Bearer ${apiKey}`,
  },
});

if (!response.ok) {
  throw new Error(`Mianotes API returned ${response.status}`);
}

const results = await response.json();
console.log(results);
```

## Use the token from Python

```python
import os
import urllib.parse
import urllib.request

api_url = os.environ.get("MIANOTES_API_URL", "http://127.0.0.1:8200")
api_key = os.environ["MIANOTES_API_KEY"]
query = urllib.parse.urlencode({"q": "settings"})

request = urllib.request.Request(
    f"{api_url}/api/search?{query}",
    headers={"Authorization": f"Bearer {api_key}"},
)

with urllib.request.urlopen(request) as response:
    print(response.read().decode("utf-8"))
```

## Use the token with MCP

The bundled MCP server reads the same environment variables:

```bash
export MIANOTES_API_URL="http://127.0.0.1:8200"
export MIANOTES_API_KEY="mia_paste_the_key_here"
mianotes-mcp
```

If your MCP client starts the server from a different shell, make sure that
shell can see the same environment variables.

## Service keys and scoped tokens

`MIANOTES_API_KEY` is the service-wide key. It is best for trusted local agents,
MCP servers, and scripts that should act with admin-level access to the current
Mianotes instance.

Mianotes also supports scoped per-user API tokens through `/api/tokens`. Use
scoped tokens when a tool should have narrower permissions, such as read-only
note access.

Create a scoped token:

```bash
curl -sS \
  -X POST \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Read-only search client",
    "scopes": ["notes:read", "folders:read", "tags:read"]
  }' \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/tokens"
```

Example response:

```json
{
  "id": "8d70ce3f-e0b9-47f8-a72d-3ad3cc3cc61f",
  "name": "Read-only search client",
  "token_prefix": "mia_abc12345",
  "scopes": ["notes:read", "folders:read", "tags:read"],
  "token": "mia_raw_scoped_token_returned_once"
}
```

The raw scoped token is also returned only once.

## Common checks

Check that your shell has the key:

```bash
test -n "${MIANOTES_API_KEY}" && echo "Mianotes API key is set"
```

Check that the service is reachable:

```bash
curl -sS "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/health"
```

Check authentication:

```bash
curl -i \
  -H "Authorization: Bearer ${MIANOTES_API_KEY}" \
  "${MIANOTES_API_URL:-http://127.0.0.1:8200}/api/auth/session"
```

If you get `401`, the bearer token is missing or invalid.

If you get `403`, the token was accepted but does not have the required scope
for that endpoint.

## Keep tokens private

Do not commit API tokens to git. Do not paste real tokens into examples,
screenshots, issues, or logs.

If a token may have been exposed, create a new key and update the environments
used by your agents and tools.
