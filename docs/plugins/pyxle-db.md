# pyxle-db

> 🚧 **Coming soon — not yet released.**
>
> `pyxle-db` is being developed in internal beta and is **not** available on PyPI yet. There is nothing to `pip install` today. This page is a placeholder so we can link to it from the plugin docs once the package ships.

## What it will be

A SQLite-first database plugin for Pyxle:

- A single `Database` instance shared across loaders and actions, registered through the [plugin system](../guides/plugins.md).
- Connection pooling and PRAGMA hardening tuned for the Pyxle request lifecycle.
- Filesystem-driven migrations (`migrations/0001-init.sql`, `0002-…`) with checksum tracking so a committed migration can't be silently edited.
- A `get_database()` shortcut so app code stays terse:

  ```python
  from pyxle_db import get_database

  @server
  async def load(request):
      db = get_database()
      row = await db.fetchone("SELECT id, title FROM posts WHERE id = ?", (request.path_params["id"],))
      return {"post": dict(row) if row else None}
  ```

## Status

- **Source**: internal repo — not public yet.
- **PyPI**: not published.
- **ETA**: very soon. Subscribe on [pyxle.dev](https://pyxle.dev) to be notified when it lands.

## See also

- [Plugins guide](../guides/plugins.md) — plugin system overview.
- [Plugins API reference](../reference/plugins-api.md) — the API third-party plugins build on today.
