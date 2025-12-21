# `pyxle.config.json`

Pyxle reads this file at startup (via `pyxle.config.load_config`) to configure directories, ports, middleware, and global assets. Missing keys fall back to sensible defaults.

```json
{
  "pagesDir": "pages",
  "publicDir": "public",
  "buildDir": ".pyxle-build",
  "starlette": { "host": "127.0.0.1", "port": 8000 },
  "vite": { "host": "127.0.0.1", "port": 5173 },
  "debug": true,
  "middleware": [],
  "routeMiddleware": {
    "pages": [],
    "apis": []
  },
  "styling": {
    "globalStyles": [],
    "globalScripts": []
  }
}
```

## Fields

| Key | Type | Description |
| --- | --- | --- |
| `pagesDir` | string | Where `.pyx` files live (default `pages`). |
| `publicDir` | string | Static assets served verbatim (default `public`). |
| `buildDir` | string | Location of `.pyxle-build`; usually left alone. |
| `starlette.host/port` | string/int | Bind address for Starlette (`pyxle dev` + `pyxle serve`). |
| `vite.host/port` | string/int | Where Vite runs (dev only). |
| `debug` | bool | Enables overlay, Vite proxy, and verbose logging. Forced to `False` during `pyxle build/serve`. |
| `middleware` | string[] | Dotted paths to callables returning `starlette.middleware.Middleware`. |
| `routeMiddleware.pages/apis` | string[] | Dotted paths to route hook callables (see [custom middleware](../data/middleware-hooks.md)). |
| `styling.globalStyles` | string[] | Paths to CSS files copied + watched globally. |
| `styling.globalScripts` | string[] | Paths to JS files copied + watched globally. |

## Validation rules

Defined in `pyxle/config.py`:

- Unknown top-level keys raise `ConfigError`.
- Ports must be integers within `1-65535`.
- Paths must be non-empty strings.
- `styling` and `routeMiddleware` must be objects with the listed properties.

## CLI overrides

`pyxle dev`, `pyxle build`, and `pyxle serve` expose flags that map directly to config fields. For example, `pyxle dev --port 9000 --vite-port 5174` overrides the default ports for that run only.

## Compare with Next.js

Equivalent to `next.config.js`, but kept in JSON so Python tooling can parse it without executing arbitrary code. Keep environment-specific tweaks outside the file (e.g., pass `--host 0.0.0.0` in staging) to avoid committing secrets.

### Multiple config files

- `pyxle dev --config pyxle.local.json`
- `pyxle build --config pyxle.production.json`

Store shared defaults in the base file and keep overrides minimal (ports, middleware, analytics flags, etc.).

---
**Navigation:** [← Previous](cli.md) | [Next →](../internals/index.md)
