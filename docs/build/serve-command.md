# `pyxle serve`

After running `pyxle build`, use `pyxle serve` to host the compiled app without starting Vite. The command lives in `pyxle/cli/__init__.py` and reuses the same Starlette app that powers the dev server—just without debug middleware or the overlay.

## Typical workflow

```bash
pyxle build
pyxle serve --host 0.0.0.0 --port 8080
```

- Runs the build first (unless `--skip-build`).
- Loads `dist/page-manifest.json` to map routes to hashed client bundles.
- Mounts `dist/public` at `/` and `dist/client` at `/client` so browsers download production assets.
- Starts Uvicorn with `reload=False` and `debug=False`.

## Options

| Option | Description |
| --- | --- |
| `--dist-dir PATH` | Serve a custom distribution directory (defaults to `<project>/dist`). |
| `--skip-build` | Assume artifacts already exist; useful in CI/CD where the build happens earlier. |
| `--serve-static/--no-serve-static` | When false, Pyxle skips mounting `dist/public` and `dist/client`; use if a CDN handles static assets. |
| `--host`, `--port` | Override Starlette listen address just like `pyxle dev`. |
| `--config` | Load settings from another `pyxle.config.json`. |

## Internals

1. Loads production config (`debug=False`).
2. Optionally runs `run_build()` to refresh artifacts.
3. Reads `page-manifest.json` via `pyxle.build.manifest.load_manifest()`.
4. Calls `build_metadata_registry()` + `build_route_table()` to recreate route metadata.
5. Calls `create_starlette_app()` with `serve_static` toggle so Starlette either serves assets or defers to your CDN.

## Compare with Next.js

Analogous to `next start`: you get a Starlette/uvicorn server that reads precompiled artifacts. Because Starlette is pure ASGI, you can also deploy the same app with Hypercorn, Daphne, or another ASGI host if you wrap it yourself.

Next steps:
- Automate Tailwind + Pyxle builds in CI.
- Put a reverse proxy (nginx, Caddy) or serverless container (Fly.io, Railway) in front of `pyxle serve`.

### Health check endpoint

Expose `pages/api/health.py` so load balancers can hit `/api/health`. Starlette shares the same process as your pages, so the endpoint doubles as a liveness probe.

---
**Navigation:** [← Previous](production-build.md) | [Next →](../deployment/index.md)
