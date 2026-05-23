# Storage and database

Mianotes uses SQLite by default. The database file is named `mia.db` and lives inside the active Mianotes data folder.

## Default database

On first start, Mianotes creates a runtime `storage.json` file in the web service root if it does not already exist.

A fresh install uses:

```text
data/mia.db
```

The `data/` folder contains the active database, Markdown notes, source files, and folder directories.

## `storage.json`

`storage.json` controls which local database folder the instance is using.

Example:

```json
{
  "activeLocation": "default",
  "databaseFile": "mia.db",
  "allowedStorageLocations": [
    {
      "id": "default",
      "name": "Main workspace",
      "folderPath": "/Users/example/Mianotes/data"
    }
  ]
}
```

Each location points to a folder that contains, or can contain, a `mia.db` database. Each database has its own notes, folders, users, settings, sessions, tokens, jobs, and agent activity.

## Why `storage.example.json` exists

The repository includes `storage.example.json` as a template only. It is safe to commit because it does not represent a real user machine.

The real `storage.json` is created and updated by each installation. It is ignored by Git because it can contain local filesystem paths that only make sense on that computer or server.

If an admin creates a service API key from the Settings screen or
`POST /api/settings/api-key`, the real `storage.json` also contains an `apiKey`
field with the raw service key. This is what lets a UI-generated key survive a
service restart. The active database stores only the derived public verifier
used to check presented bearer tokens.

Do not commit the real `storage.json`.

## Switching database

Admins can switch databases from the Settings screen.

When the active database changes, Mianotes:

1. updates `storage.json`;
2. rebinds the service to the selected `mia.db`;
3. creates the database schema if the selected database is empty;
4. ends the current browser session;
5. asks the user to sign in again.

Ending the session is intentional. Each database has its own users and passwords.

## Creating a new database

If no other databases are available, the Settings screen can create a new database in an allowed folder.

Mianotes creates `mia.db` in that folder and initialises the schema. The first user who joins the new database becomes the admin for that database.

## Advanced configuration

Most installs should leave `MIANOTES_DATABASE_URL` empty.

To force a database URL:

```env
MIANOTES_DATABASE_URL=sqlite:////absolute/path/to/mia.db
```

To force a data folder:

```env
MIANOTES_DATA_DIR=/absolute/path/to/mianotes-data
```

When `MIANOTES_DATA_DIR` is set and `MIANOTES_STORAGE_CONFIG_PATH` is not set, Mianotes uses that folder directly instead of reading `storage.json`. This is mainly useful for tests and scripted deployments.

## Files that should stay private

Do not commit these to a public repository:

```text
storage.json
data/
mia.db
.env
```

Database files are never served by the file API. Source and Markdown files are served through controlled routes, but `mia.db` is blocked.
