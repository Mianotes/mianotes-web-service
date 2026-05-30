# Storage folders and database

Mianotes uses SQLite by default. In the UI, admins choose local workspaces. Inside each workspace, Mianotes keeps private runtime data in a hidden `.mianotes/` directory.

## Default databases

On first start, Mianotes creates a runtime `workspaces.json` file in the web service root if it does not already exist.

A fresh install uses:

```text
data/system.db
data/.mianotes/mia.db
```

`data/system.db` stores global users, sessions, API key verification, and global settings.

`data/.mianotes/mia.db` is the default workspace database. Workspace folders contain Markdown notes, source files, folder directories, and the hidden `.mianotes/` directory.

Mianotes also writes a `.gitignore` into each selected storage folder:

```text
.mianotes/
.mianotes/mia.db
mia.db
system.db
system.db-wal
system.db-shm
system.db-journal
```

This keeps private runtime data out of Git repositories when users choose a project folder.

## `workspaces.json`

`workspaces.json` lists the local workspaces available to the app.

Example:

```json
{
  "activeLocation": "default",
  "databaseFile": ".mianotes/mia.db",
  "allowedStorageLocations": [
    {
      "id": "default",
      "name": "Main workspace",
      "folderPath": "/Users/example/Mianotes/data"
    }
  ]
}
```

Each location points to a workspace folder that contains, or can contain, a `.mianotes/mia.db` database. Each workspace has its own notes, folders, tags, source records, jobs, shares, and publishing history.

Users, sessions, API keys, and global settings live in `data/system.db`.

## Runtime workspace config

The real `workspaces.json` is created and updated by each installation. It is ignored by Git because it can contain local filesystem paths that only make sense on that computer or server.

`workspaces.json` must not contain raw API keys or other secrets. Service API keys
are shown once, copied into the environment that needs them, and verified
through a public hash stored in `data/system.db`.

Do not commit the real `workspaces.json`.

## Switching workspaces

All signed-in users can switch workspace from the workspace switcher next to the breadcrumb. Admins can add workspaces from Settings.

When a user switches workspace, Mianotes:

1. stores the selected workspace on that user's session;
2. routes workspace-content API calls to the selected `.mianotes/mia.db`;
3. keeps the browser session signed in;
4. leaves other users on their own selected workspace.

Switching workspace is per user session. It is not global process state.

## Creating a new workspace

Admins can add a new local workspace from Settings.

Mianotes creates `.mianotes/mia.db` inside that workspace and initialises the workspace schema. Users remain global and can use the new workspace without signing up again.

## Advanced configuration

Most installs should leave `MIANOTES_DATABASE_URL` empty.

To force a database URL:

```env
MIANOTES_DATABASE_URL=sqlite:////absolute/path/to/.mianotes/mia.db
```

To force a data folder:

```env
MIANOTES_DATA_DIR=/absolute/path/to/mianotes-data
```

When `MIANOTES_DATA_DIR` is set and `MIANOTES_STORAGE_CONFIG_PATH` is not set, Mianotes uses that folder as the default workspace folder and creates `data/system.db` for global state. This is mainly useful for tests and scripted deployments.

## Private files

Do not commit these to a public repository:

```text
workspaces.json
data/
.mianotes/
mia.db
system.db
.env
```

Database files are never served by the file API. Source and Markdown files are served through controlled routes, but `mia.db`, `system.db`, and their SQLite sidecars are blocked.
