# Security

Mianotes supports two ways to access protected APIs:

- Browser users sign in through the dashboard and use a cookie-based session created by the login flow.
- Agents and API clients use a per-user API token sent as a bearer token:

```http
Authorization: Bearer mia_...
```

Protected APIs, including file uploads, require either a valid browser session or a valid API token with the required scope. This authenticates the caller, but it does not sandbox the caller.

## Agent access

Mianotes is designed to work with local agents, MCP clients, scripts, and API clients. These tools can save notes, upload files, index links, search stored knowledge, and ask Mia to process note content.

Treat any agent with a valid Mianotes token as trusted. If an agent can read a sensitive file on the local machine, Mianotes cannot prevent that agent from uploading the file contents as text, a renamed file, or a generated note.

For example, if an agent can read a private key, credentials file, or `.env` file, it can copy that content and send it to Mianotes. Mianotes can authenticate the request and audit who sent it, but it cannot prove where uploaded bytes originally came from.

## Best practices for agents

- Do not give untrusted agents filesystem access to sensitive files.
- Run agents with the least filesystem access they need.
- Give agents project-specific working directories instead of access to a whole home directory.
- Use scoped API tokens for agents instead of sharing browser sessions.
- Revoke an agent token when the agent no longer needs access.
- Avoid giving hosted or third-party agents direct access to local folders unless you trust the agent and its operator.
- Review activity logs after allowing a new agent or automation to use Mianotes.

## File uploads and parsing

Mianotes uses MarkItDown as part of its file parsing pipeline. MarkItDown runs with the privileges of the Mianotes service process. For that reason, Mianotes should only pass MarkItDown files that are controlled by Mianotes, such as uploaded source files saved under the Mianotes data directory.

Mianotes should not expose APIs or MCP tools that accept arbitrary local filesystem paths such as:

```text
/Users/example/.ssh/id_rsa
/etc/passwd
../../secrets.env
```

API and MCP clients should upload file bytes, submit URLs, submit text, or reference existing Mianotes source files by ID. They should not be able to ask Mianotes to parse arbitrary paths outside the Mianotes data directory.

## URL indexing

URL ingestion fetches data from the network. Admins can configure blocked domains to prevent Mianotes from fetching URLs from sensitive or disallowed hosts.

Recommended blocked targets include:

- Internal metadata services.
- Private administration panels.
- Internal-only hostnames.
- Domains that should never be indexed into shared knowledge.

Hosted deployments should also consider blocking private network ranges unless the instance is intentionally allowed to index internal resources.

## Path blocklist

Admins can configure blocked file paths to reduce the risk of accidental or agent-driven uploads from sensitive locations.

Examples of paths commonly worth blocking:

```text
~/.ssh
~/.aws
~/.config
~/.kube
*.pem
*.key
.env
credentials.json
```

Path blocklists are a safety net, not a complete sandbox. A trusted local agent that can read a blocked file may still copy the contents elsewhere and upload them under a different name.

## Activity auditing

Mianotes records activity metadata so admins can review how the system is being used. The Activity screen lets admins audit:

- Who uploaded a file.
- When the upload happened.
- The original filename.
- The source type.
- Which note or folder the upload belongs to.
- Which user or agent token performed the action.

Audit logs help with accountability and investigation, but they do not prevent a trusted caller from sending data it can already access.

## Deployment

For local-only use, bind the service to `127.0.0.1`.

Only bind Mianotes to `0.0.0.0` or another network interface when you understand the security implications. On a LAN or hosted server, anyone who can reach the service can reach the login page and attempt to authenticate.

Recommended deployment practices:

- Use a dedicated operating system user for the Mianotes service.
- Store Mianotes data in a directory owned by that service user.
- Do not run Mianotes as `root`.
- Use a firewall when exposing Mianotes on a network.
- Use HTTPS when hosting Mianotes beyond a trusted local network.
- Keep API tokens private and rotate them if they may have been exposed.

## What Mianotes can and cannot protect

Mianotes can:

- Require authentication for protected APIs.
- Require scoped API tokens for agents.
- Store source metadata for auditability.
- Restrict parsing to Mianotes-controlled files.
- Block configured file paths and domains.
- Let admins review activity.

Mianotes cannot:

- Sandbox an agent that already has access to sensitive local files.
- Prove that uploaded content did not come from a secret file.
- Stop a trusted local process from copying data it can already read.
- Replace operating system permissions, firewall rules, or agent sandboxing.
