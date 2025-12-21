# File-based Routing

Pyxle inspects everything under `pages/` and turns filenames into Starlette routes using `pyxle/routing/paths.py`. The rules intentionally mirror Next.js:

| File | Route |
| --- | --- |
| `pages/index.pyx` | `/` |
| `pages/blog/index.pyx` | `/blog` |
| `pages/blog/[slug].pyx` | `/blog/{slug}` |
| `pages/docs/[...segments].pyx` | `/docs/{segments:path}` |
| `pages/(marketing)/hero.pyx` | `/hero` (route groups ignored) |

### How it works

1. `pyxle/devserver/scanner.py` categorises each file as page, API, or client asset.
2. `route_path_variants_from_relative()` converts the relative path into a `RoutePathSpec` with a primary path and optional aliases (used for optional catch-alls such as `[[...slug]]`).
3. `pyxle/devserver/routes.py` builds `PageRoute` entries containing the path, loader metadata, and compiled module locations.
4. `create_starlette_app()` registers each route on a Starlette `Router`.

### Route groups

Folders wrapped in parentheses, e.g. `pages/(marketing)/cta.pyx`, are omitted from the URL just like Next.js route groups. Use them to organise files without changing the public path.

### Index collapsing

If a folder contains `index.pyx`, the compiler collapses the `index` segment so `pages/blog/index.pyx` becomes `/blog` rather than `/blog/index`.

### Custom middleware per route set

Use `pyxle.config.json`:

```json
{
  "routeMiddleware": {
    "pages": ["middlewares.telemetry.apply_csp"],
    "apis": ["middlewares.telemetry.attach_request_id"]
  }
}
```

Each dotted path should expose a callable returning `starlette.middleware.Middleware`. See [Custom middleware & route hooks](../data/middleware-hooks.md) for details.

## Compare with Next.js

- Identical filename semantics, including dynamic parameters, catch-alls, and route groups.
- There is no `metadata/` or `head.tsx` file; use the [Head management](../runtime/head-management.md) guide instead.

For dynamic segments and catch-alls, continue to [Dynamic segments](dynamic-segments.md).
