# Database

Mianotes uses SQLite by default. The database file is named `mia.db` and lives
inside the active Mianotes data folder.

## Default database

On first start, Mianotes creates a runtime `storage.json` file in the web
service root if it does not already exist. The default file points to `./data`,
so a fresh install uses:

```text
data/mia.db
```

The `data/` folder contains the active database, Markdown notes, source files,
and folder directories.

## storage.json

`storage.json` controls which local database folder the instance is using. A
typical file looks like this:

```json
{
  "activeLocation": "default",
  "databaseFile": "mia.db",
  "allowedStorageLocations": [
    {
      "id": "default",
      "name": "Main workspace",
      "folderPath": "/Users/federico/Desktop/Mianotes/code/mianotes-web-service/data"
    }
  ]
}
```

Each location points to a folder that contains, or can contain, a `mia.db`
database. Each database has its own notes, folders, users, settings, sessions,
tokens, jobs, and agent activity.

## Why storage.example.json exists

The repository includes `storage.example.json` as a template only. It is safe to
commit because it does not represent a real user machine.

The real `storage.json` is created and updated by each installation. It is
ignored by Git because it can contain local filesystem paths that only make
sense on that computer or server.

## Switching database

Admins can switch databases from the Settings screen. The dashboard reads the
allowed storage locations from the web service, then lets the admin select
another database folder.

When the active database changes, Mianotes:

- updates `storage.json`
- rebinds the service to the selected `mia.db`
- creates the database schema if the selected database is empty
- ends the current browser session
- asks the user to sign in again

Ending the session is intentional. Each database has its own users and
passwords, so the browser must authenticate against the newly selected
database.

## Creating a new database

If no other databases are available, the Settings screen can create a new
database in an allowed folder. Mianotes creates `mia.db` in that folder and
initialises the schema.

The first user who joins the new database becomes the admin for that database.

## Security

Database files are never served by the file API. Source and Markdown files are
served through controlled routes, but `mia.db` is blocked.

Do not commit `storage.json`, `data/`, or `mia.db` to a public repository.

## Advanced configuration

Most installs should leave `MIANOTES_DATABASE_URL` empty.

If `MIANOTES_DATABASE_URL` is set, it takes precedence over `storage.json` and
Mianotes uses that database URL directly:

```text
MIANOTES_DATABASE_URL=sqlite:////absolute/path/to/mia.db
```

This is useful for advanced deployments, but the normal local setup should use
the Settings screen and `storage.json`.

`MIANOTES_DATA_DIR` can also point the service at a specific data folder:

```text
MIANOTES_DATA_DIR=/absolute/path/to/mianotes-data
```

When `MIANOTES_DATA_DIR` is set and `MIANOTES_STORAGE_CONFIG_PATH` is not set,
Mianotes uses that folder directly instead of reading `storage.json`. This is
mainly useful for tests and scripted deployments.
