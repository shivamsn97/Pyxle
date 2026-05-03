# pyxle-db

SQLite-first database plugin for Pyxle. Ships connection pooling, PRAGMA hardening, and filesystem-driven migrations with checksum tracking.

- **Package**: [`pyxle-db`](https://pypi.org/project/pyxle-db/)
- **Source**: `pyxle-framework/pyxle-plugins/packages/pyxle-db`
- **Requires**: `pyxle-framework >= 0.3.0`

## Install

```bash
pip install pyxle-db
```

Then list it in `pyxle.config.json`:

```json
{
  "plugins": [
    {
      "name": "pyxle-db",
      "settings": {
        "path": "./data/app.db",
        "migrationsDir": "migrations"
      }
    }
  ]
}
```

Paths are resolved relative to the project root. List `pyxle-db` **before** any plugin that depends on it (e.g. `pyxle-auth`).

## Using the database from your app

```python
from pyxle_db import get_database

@server
async def load(request):
    db = get_database()
    row = await db.fetchone(
        "SELECT id, title FROM posts WHERE id = ?",
        (request.path_params["id"],),
    )
    return {"post": dict(row)} if row else {"post": None}
```

`get_database()` returns the `Database` instance the plugin opened at startup. It's the same instance for every request — Pyxle's connection pool handles thread-safety under concurrent loads.

## Writing data

Always use transactions for writes:

```python
from pyxle_db import get_database

@action
async def create_post(request):
    db = get_database()
    body = await request.json()
    async with db.transaction() as tx:
        tx.execute(
            "INSERT INTO posts (id, title, body) VALUES (?, ?, ?)",
            (body["id"], body["title"], body["body"]),
        )
    return {"ok": True}
```

Inside the `async with` block, `tx.execute` / `tx.fetchone` / `tx.fetchall` all run inside the same transaction. Exceptions roll back automatically.

## Config reference

Every setting is optional:

| Key | Type | Default | Description |
|---|---|---|---|
| `path` | `string` | `"./data/app.db"` | Relative or absolute path to the SQLite file. The parent directory is created if it doesn't exist. |
| `migrationsDir` | `string` | `"migrations"` | Directory of ordered `.sql` migration files. Skipped silently if the directory doesn't exist. |
| `waitForFileMs` | `integer` | `0` | Poll for the DB file to exist before opening (useful when another process is about to create it). Default 0 = don't wait. |

## Registered services

| Service name | Type | Returned by |
|---|---|---|
| `db.database` | `Database` | [`get_database()`](#using-the-database-from-your-app) / `plugin("db.database")` |
| `db.path` | `Path` | `plugin("db.path")` — useful for logging or diagnostic pages |

## Migrations

Place migration files in the directory configured via `migrationsDir`. Each file is named `<NNN>-<slug>.sql` — numeric prefix controls ordering:

```
migrations/
├── 0001-initial-schema.sql
├── 0002-add-users-table.sql
└── 0003-add-email-index.sql
```

At startup the plugin:

1. Creates a `schema_migrations` tracking table (if absent).
2. Applies every file whose prefix isn't already in the table, in ascending order.
3. Stores each migration's SHA-256 in `schema_migrations.checksum`.

**Editing a committed migration is rejected.** If the on-disk SHA-256 no longer matches the stored checksum, startup raises `MigrationChecksumMismatch`. The correct fix is a follow-up migration (`0004-fix-thing.sql`), never editing `0003`.

Multi-statement files are fine — the plugin splits on semicolons outside of strings and comments.

## Operations & troubleshooting

### `MigrationChecksumMismatch`

Someone edited an applied migration. Revert the file to its original content, or if the edit is genuinely needed, write a new migration that applies the correction.

### The DB file isn't being created

Check `db.path` — make sure the parent directory is writable. The plugin creates the parent directly via `Path.mkdir(parents=True)`, so the most common cause is a read-only mount or an absolute path typo.

### "Database is locked" during heavy writes

SQLite serialises writers. If you're seeing contention, move expensive batch writes into a single transaction so the lock is held once instead of per-statement:

```python
async with db.transaction() as tx:
    tx.executemany("INSERT INTO events (...) VALUES (?, ?, ?)", rows)
```

## Direct instantiation (without the plugin system)

You can import the library without listing it as a plugin:

```python
from pyxle_db import connect

db = await connect("app.db", migrations_dir="migrations")
```

This is the right choice for CLI scripts, tests, or apps that want multiple independent databases. The plugin is just a convenience wrapper that saves you from wiring `connect()` into a shared lifecycle hook — use it when the app wants exactly one database, skip it otherwise.

## See also

- [Plugins guide](../guides/plugins.md) — plugin system overview.
- [Plugins API reference](../reference/plugins-api.md) — `PluginContext`, `plugin(name)` lookup.
- [pyxle-auth](pyxle-auth.md) — depends on pyxle-db.
