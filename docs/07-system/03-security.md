# Security

Mianotes is local-first, but local-first does not mean risk-free. Treat any user, agent, or script with a valid Mianotes token as trusted.

## Access methods

Protected APIs can be accessed by:

- browser users with a cookie-based session;
- local agents using the service-wide `MIANOTES_API_KEY` from `.env`;
- narrower automations using scoped per-user API tokens.

Bearer tokens are sent as:

```http
Authorization: Bearer <token>
```

The service-wide token is private. Mianotes stores only a derived public hash in each `mia.db`, so the same running service can switch databases without storing the raw token in any database.

## What authentication does and does not do

Authentication verifies the caller. It does not sandbox the caller.

If an agent can read a sensitive file on the local machine, Mianotes cannot prevent that agent from uploading the file contents as text, a renamed file, or a generated note.

Mianotes can audit who sent data. It cannot prove where uploaded bytes originally came from.

## Best practices for agents

- Do not give untrusted agents filesystem access to sensitive files.
- Run agents with the least filesystem access they need.
- Give agents project-specific working directories instead of access to a whole home directory.
- Use `MIANOTES_API_KEY` only for trusted local agents.
- Use scoped per-user tokens when an automation needs narrower access.
- Revoke agent tokens when agents no longer need access.
- Avoid giving hosted or third-party agents direct access to local folders unless you trust the agent and its operator.
- Review activity logs after allowing a new agent or automation to use Mianotes.

## File uploads and parsing

Uploaded files are first saved into the Mianotes data directory, then parsed from that controlled location.

Mianotes APIs and MCP tools accept uploaded file bytes, URLs, text, or existing Mianotes source file IDs. They do not provide a general-purpose endpoint for reading arbitrary local filesystem paths from the server.

This prevents clients from asking the Mianotes service to parse arbitrary host paths.

## URL indexing

URL ingestion fetches data from the network. Admins can configure blocked domains to prevent Mianotes from fetching URLs from sensitive or disallowed hosts.

Recommended blocked targets include:

- internal metadata services;
- private administration panels;
- internal-only hostnames;
- domains that should never be indexed into shared knowledge.

Hosted deployments should also consider blocking private network ranges unless the instance is intentionally allowed to index internal resources.

## Path blocklist

Admins can configure blocked file paths to reduce accidental or agent-driven uploads from sensitive locations.

Path blocklists are a safety net, not a complete sandbox. A trusted local agent that can read a blocked file may still copy the contents elsewhere and upload them under a different name.

## Activity auditing

The Activity screen lets admins audit:

- who uploaded a file;
- when the upload happened;
- the original filename;
- the source type;
- which note or folder the upload belongs to;
- which user or agent token performed the action.

Audit logs help with accountability and investigation, but they do not prevent a trusted caller from sending data it can already access.

## Deployment guidance

For local-only use, bind the service to:

```text
127.0.0.1
```

Only bind Mianotes to `0.0.0.0` or another network interface when you understand the security implications.

Recommended deployment practices:

- use a dedicated operating system user for the Mianotes service;
- store Mianotes data in a directory owned by that service user;
- do not run Mianotes as `root`;
- use a firewall when exposing Mianotes on a network;
- use HTTPS when hosting beyond a trusted local network;
- keep API tokens private and rotate them if exposed.

## What Mianotes can protect

Mianotes can:

- require authentication for protected APIs;
- require bearer API tokens for agents;
- store source metadata for auditability;
- restrict parsing to Mianotes-controlled files;
- block configured file paths and domains;
- let admins review activity.

Mianotes cannot:

- sandbox an agent that already has access to sensitive local files;
- prove that uploaded content did not come from a secret file;
- stop a trusted local process from copying data it can already read;
- replace operating system permissions, firewall rules, or agent sandboxing.
