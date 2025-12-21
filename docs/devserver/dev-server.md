# Dev Server Architecture

`pyxle dev` coordinates four subsystems:

1. **Config loading** – `pyxle.config.load_config()` reads `pyxle.config.json`, merges CLI overrides, and feeds the result into `DevServerSettings`.
2. **Incremental builder** – `pyxle/devserver/build.py` orchestrates compilation by scanning `pages/`, copying API modules, syncing client assets, and writing metadata.
3. **Starlette app** – `pyxle/devserver/starlette_app.py` assembles routers, middleware, global styles/scripts, and the Vite proxy.
4. **Watchdog** – `pyxle/devserver/watcher.py` debounces filesystem events and triggers rebuilds.

## Startup flow

```
pyxle dev
└── load_config(project_root)
    └── DevServerSettings.from_project_root()
        └── DevServer(settings).start()
            ├── build_once(settings, force_rebuild=True)
            ├── create_starlette_app(...)
            ├── start Vite dev server proxy
            └── ProjectWatcher.start()
```

The dev server exposes Starlette on `http://<host>:<port>` (default `127.0.0.1:8000`) and proxies client asset requests to Vite at `http://<vite_host>:<vite_port>`.

## Builder highlights

- Uses content hashes to skip unchanged files (`CachedSourceRecord`).
- Keeps `.pyxle-build` directories warm so restarts are cheap.
- Writes layout metadata, global stylesheets, and client bootstrap files every run to guarantee consistency.

## Static assets

`StaticAssetsMiddleware` (see `starlette_app.py`) serves `/public/*` and `/client/*` before hitting Starlette routes. In dev, `/client` proxies to Vite; in production it serves the built files under `dist/client`.

## Compare with Next.js

Think of `pyxle dev` as `next dev` split into Starlette (for Python loaders/APIs) and Vite (for React). Instead of a single Node server, you get:

- Hot reload for Python via Watchdog.
- Vite overlay for JSX errors.
- Pyxle overlay for loader/API stack traces.

Deep dive into [Overlay & watchers](overlay-and-watchers.md) for diagnostics.
