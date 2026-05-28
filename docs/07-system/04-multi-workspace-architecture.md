# Multi-workspace architecture

This document describes the architecture for supporting multiple Mianotes workspaces from one running app.

## Goal

Mianotes should let one running app manage multiple workspaces.

A workspace is a top-level knowledge area with its own local folder and its own content database.

Use "workspace" for the top-level knowledge area. Keep "folder" for folders inside a workspace. Remove "instance" from user-facing copy, docs, and app language.

## Core model

Mianotes separates global app state from workspace content.

Global app state lives in:

```text
data/system.db
```

Workspace content lives in each workspace folder:

```text
<workspace>/.mianotes/mia.db
```

The selected workspace belongs to the user session or request. It must never be global process state.

## Global system database

`data/system.db` stores app-wide data only:

- users
- sessions
- API key
- global settings
- runtime state needed before a workspace is selected

Users are global in this version. There is no workspace membership model.

A signed-in user can switch between available workspaces without signing out.

## Workspace databases

Each workspace has its own `.mianotes/mia.db`.

The workspace database stores workspace-specific data only:

- folders
- notes
- tags
- comments
- source file records
- jobs
- file paths
- share records
- workspace metadata
- publishing history and generated-site metadata

Workspace data must not be stored in `data/system.db`.

Global users, sessions, and API keys must not be stored in workspace databases.

Workspace rows that reference a user should store the global `user_id` as a string reference. The API is responsible for hydrating user details from `system.db`.

## Workspace configuration

Rename `storage.json` to `workspaces.json`.

`workspaces.json` is the editable and bootstrap source of truth for available workspaces. `system.db` stores runtime and session state, but not the workspace registry in this version.

The existing JSON shape should stay the same.

Admins can add workspaces from Settings or by editing `workspaces.json`.

Normal users can switch between existing workspaces, but cannot add new ones.

Mianotes must not remove workspace folders or workspace databases from disk. Avoid destructive workspace deletion in the UI.

## Creating a workspace

When an admin adds a workspace, Mianotes should:

1. create or initialise the workspace folder;
2. create the hidden `.mianotes/` folder if needed;
3. create or initialise `<workspace>/.mianotes/mia.db`;
4. run workspace migrations against that workspace database;
5. add the workspace to `workspaces.json`;
6. show the workspace as available in the web app.

The app should also ensure the workspace folder has a `.gitignore` entry for `.mianotes/`.

## Switching workspace

The web app should let every signed-in user switch workspace.

Switching workspace keeps the current auth session.

When a user switches workspace, Mianotes stores the selected workspace on that user's session. Future workspace-content API calls use that workspace unless the request explicitly targets another workspace.

Switching workspace should show that workspace's folders, notes, jobs, source files, publishing state, share records, and workspace-specific settings.

Switching workspace for one user must not affect other users.

## API and request routing

Every request that reads or writes workspace content must resolve a workspace before touching the database.

Workspace resolution order:

1. explicit request workspace, when supported by the endpoint;
2. workspace header, for REST and agent clients;
3. selected workspace stored in the current user session;
4. default workspace from `workspaces.json`.

If no valid workspace can be resolved, the API should return a clear error.

The API must not silently fall back to the wrong workspace.

## API key and agents

There is one API key for all workspaces in this version.

The API key lives in `data/system.db`.

The same key works across all workspaces.

Agent and MCP tools must be workspace-aware. They should accept an explicit workspace argument where possible.

Mianotes skills and agent docs should support these shorthands after the workspace-aware API exists:

```text
Mia(<workspace>: <search_query>)
Mia(<workspace>/<folder>: <search_query>)
Mia(<workspace>/<folder>)
```

The first two forms are GET operations. The agent should search the selected workspace, optionally scoped to the folder, using the user's query in their own words.

The third form is a PUT operation. The agent should save the requested content into the selected workspace and folder, creating a short useful title based on the content.

If an agent cannot target the requested workspace, it should say so instead of using another workspace.

## Jobs

Jobs belong to a workspace database.

The job runner must know which workspace each job belongs to and must run the job using that workspace's database and files.

Parsing, indexing, publishing, source file handling, and Mia prompt jobs must not cross workspace boundaries.

## Files

Workspace files live under the workspace folder.

Mianotes should preserve user files and generated note files on disk whenever records are removed from the database.

Workspace database files are private and must not be served by file APIs:

```text
<workspace>/.mianotes/mia.db
```

## UI

The web app should support workspace switching without sending users to Settings.

Add a workspace switcher button next to the breadcrumb. Use a folder/workspace icon.

When clicked, the switcher opens a list of available workspaces.

All signed-in users can switch workspace from this menu.

Only admins can add workspaces from Settings.

The current workspace should always be visible in the UI.

The breadcrumb should always start with the current workspace name, including note lists, folder views, note previews, note editing, publishing, users, and settings.

Examples:

```text
Research
Research / API notes
Research / API notes / OAuth checklist
Research / API notes / OAuth checklist / Edit
Research / Settings
Research / Users
```

Settings and Users remain global app screens in this version, even though the breadcrumb starts with the current workspace for orientation.

## Permissions

Do not add workspace membership in this version.

Users are global.

Admins can manage global settings and add workspaces.

Normal users can use all available workspaces.

## Documentation

Update docs to describe the new workspace model.

Explain that:

- Mianotes has one global system database;
- each workspace has its own `.mianotes/mia.db`;
- users, sessions, and API keys are global;
- workspace content is stored per workspace;
- admins control which workspaces are available;
- switching workspace is per user session, not global process state.

Remove or rewrite user-facing references to "instance".

## Migration

No migration of existing databases is required for the first implementation of this architecture.

Start from the new model:

- initialise `data/system.db`;
- initialise the default workspace at `data/.mianotes/mia.db`;
- use `workspaces.json` to register available workspaces.

Existing files must not be deleted.

## Out of scope

Do not add these in this version:

- workspace membership;
- per-workspace permissions;
- destructive workspace deletion;
- migration of existing mixed global/workspace databases;
- cross-workspace search unless explicitly requested and designed later.

## Acceptance criteria

- Mianotes uses `data/system.db` for global users, sessions, API key, and global settings.
- `workspaces.json` is the editable source of truth for available workspaces.
- Each workspace has its own `.mianotes/mia.db`.
- Users can switch workspace without signing out.
- Workspace switching is per user session and does not affect other users.
- The current workspace is visible in the breadcrumb.
- The breadcrumb always starts with the current workspace.
- A workspace switcher is available next to the breadcrumb.
- Admins can add workspaces.
- Normal users can switch between existing workspaces.
- The app does not delete workspace folders or workspace databases.
- The existing `workspaces.json` shape is preserved.
- The API key works across all workspaces.
- Agent and MCP access can target a workspace explicitly.
- User-facing copy uses "workspace" for the top-level knowledge area.
- User-facing copy keeps "folder" for folders inside a workspace.
- User-facing copy does not use "instance".
- No workspace membership model is added in this version.
