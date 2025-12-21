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

## Runtime wiring diagram

```
    file save                       HTTP request
pages/ --------▶ Watchdog ──┐           from browser
                 │                 │
public/ -------▶ Watchdog ───┼─▶ build_once ───┼──▶ Starlette router ─▶ loader/SSR
global styles/scripts ───────┘                 │
                          └──▶ Vite proxy ─▶ Vite dev server

Rebuild summary ─▶ Overlay websocket ─▶ Browser overlay UI
```

- **Watchdog** pushes debounced file lists into `build_once`, which recompiles changed `.pyx` files and syncs styles/scripts.
- **Starlette** serves API + page routes straight from the freshly-written `.pyxle-build/server` directory.
- **Vite proxy** only receives requests ending in `.js`, `.css`, `@vite/client`, etc., while everything else falls through to Starlette.
- **Overlay manager** notifies browsers about rebuilds (`reload` events) or uncaught exceptions (`error` events).

## Builder highlights

- Uses content hashes to skip unchanged files (`CachedSourceRecord`).
- Keeps `.pyxle-build` directories warm so restarts are cheap.
- Writes layout metadata, global stylesheets, and client bootstrap files every run to guarantee consistency.

## Static assets

`StaticAssetsMiddleware` (see `starlette_app.py`) serves `/public/*` and `/client/*` before hitting Starlette routes. In dev, `/client` proxies to Vite; in production it serves the built files under `dist/client`.

### Sample request/response traces

```
# Page render
GET /dashboard HTTP/1.1
Host: 127.0.0.1:8000
Accept: text/html
X-Pyxle-Navigation: 0

→ Starlette page route calls compiled loader
→ ComponentRenderer shells out to Node
← HTTP/1.1 200 OK + streamed HTML

# Client asset (hot-reloaded)
GET /client/pages/dashboard.jsx?t=123 HTTP/1.1
Host: 127.0.0.1:8000
Accept: text/javascript

→ ViteProxy forwards to http://127.0.0.1:5173
← HTTP/1.1 200 OK + JS module + HMR headers
```

## Compare with Next.js

Think of `pyxle dev` as `next dev` split into Starlette (for Python loaders/APIs) and Vite (for React). Instead of a single Node server, you get:

- Hot reload for Python via Watchdog.
- Vite overlay for JSX errors.
- Pyxle overlay for loader/API stack traces.

Deep dive into [Overlay & watchers](overlay-and-watchers.md) for diagnostics.
