# Pyxle Framework Architecture

> **Vision:** Ship a "Next.js-grade" developer experience to the Python ecosystem with an intelligent single-file authoring model (`.pyx`) that unifies backend, frontend, and tooling into one cohesive workflow.

---

## 1. Product Overview

Pyxle is a Python-first full-stack framework that fuses asynchronous backend execution with modern React-based frontends. The framework ships as a Python package exposing a CLI (`pyxle`) and an ASGI application built on Starlette. Developers organize work in a `pages/` directory where file and folder names define routes, mirroring the ease of Next.js. Each `.pyx` file houses server and client logic; Pyxle transpiles these dual-mode files into runnable Python and JSX artifacts, orchestrates SSR + hydration, and provides hot reloading through an embedded Vite dev server.

### Core Principles

- **Zero Configuration** – `pyxle dev` bootstraps the entire environment end-to-end.
- **File-Based Routing** – Files inside `pages/` map directly to routes (dynamic segments supported via bracket syntax, e.g., `[id].pyx`).
- **Intelligent Single-File Authoring** – `.pyx` files co-locate async server loaders and React rendering logic.
- **Performance by Default** – SSR first render, client hydration, and asset proxying via Vite deliver fast, interactive experiences.

---

## 2. Developer Experience

### Step 1: Installation & Project Setup

```bash
# 1. Install the framework
pip install pyxle

# 2. Create a new project
pyxle init my-awesome-app
cd my-awesome-app

# 3. Generated structure
my-awesome-app/
├── pages/
│   ├── index.pyx             # Homepage (/)
│   ├── components/
│   │   └── layout.jsx        # Shared layout + helpers
│   └── api/
│       └── pulse.py          # API route (/api/pulse)
├── middlewares/
│   └── telemetry.py          # Starlette middleware registered via config
├── public/
│   ├── favicon.ico
│   ├── scripts/
│   │   └── pyxle-effects.js  # Gradient + clipboard utilities (deferred)
│   └── styles/
│       └── pyxle.css         # Dark theme styles for the starter
├── .gitignore
├── pyxle.config.json         # Project + middleware configuration
├── package.json
└── requirements.txt

# 4. Install dependencies
pyxle install  # Runs python -m pip install -r requirements.txt and npm install (use --no-python/--no-node to skip)

You can also pass `--install` to `pyxle init` to scaffold and install dependencies in
one step.
```

### Step 2: Running the Dev Server

```bash
pyxle dev
```

```text
INFO:     Pyxle dev server starting...
INFO:     Starlette server running on http://localhost:8000
INFO:     Vite server proxying from http://localhost:5173
INFO:     Watching for file changes in ./pages
```

### Step 3: Creating Content

**`pages/index.pyx`**

The starter renders a dark-mode dashboard that exercises every surface area: the loader shares utilities with the bundled API (`pages/api/pulse.py`), middleware populates `request.state`, and JSX imports a shared layout plus external CSS/JS from `public/styles/pyxle.css` and `public/scripts/pyxle-effects.js`.

Shared helpers live under `pages/components/`. Use
`pages.components.build_head()` to compose escaped `<head>` metadata and import
`RootLayout`, `Link`, or `SectionLabel` from `pages/components/layout.jsx`. See
[`docs/components.md`](docs/components.md) for details and usage tips.

The compiler captures literal `HEAD` assignments directly in the metadata JSON
for fast SSR. Whenever `HEAD` is produced by an expression (for example a
helper like `build_head()` or a variable imported from another module) the
assignment is marked as **dynamic** instead. In that case the dev server and
SSR renderer import the generated server module at request time and read the
current `HEAD` value, so helper-based declarations work out of the box.

```python
from pages.components import build_head
from pages.api.pulse import build_pulse_payload
from pyxle import __version__

HEAD = build_head(
   title="Pyxle • Minimal dark starter",
   description="Demonstrates loaders, React SSR, APIs, middleware, and static assets.",
   extra=[
      '<link rel="stylesheet" href="/styles/pyxle.css" />',
      '<script type="module" src="/scripts/pyxle-effects.js" defer></script>',
   ],
)


@server
async def load_home(request):
   pulse = build_pulse_payload()
   middleware_snapshot = getattr(request.state, "pyxle_demo", {})

   return {
      "hero": {
         "eyebrow": "PYXLE STARTER",
         "title": "Python + React in a single file.",
         "version": __version__,
      },
      "commands": [
         {"label": "Scaffold", "command": "pyxle init my-app"},
         {"label": "Run dev server", "command": "pyxle dev"},
         {"label": "Call API", "command": "curl http://localhost:8000/api/pulse"},
      ],
      "middleware": middleware_snapshot,
      "api": {
         "endpoint": "/api/pulse",
         "prefill": pulse,
         "notes": ["Loader + API share build_pulse_payload()"],
      },
   }


# --- JavaScript/PSX (Client + Server for SSR) ---
import React, { useEffect, useState } from 'react';
import { RootLayout, SectionLabel } from './components/layout.jsx';

export default function Page({ data }) {
   const [payload, setPayload] = useState(data.api.prefill);

   useEffect(() => {
      let cancelled = false;
      const refresh = async () => {
         const response = await fetch(data.api.endpoint, {
            headers: { 'x-pyxle-demo': 'pulse' },
         });
         if (!cancelled) {
            setPayload(await response.json());
         }
      };
      refresh();
      const id = window.setInterval(refresh, 8_000);
      return () => {
         cancelled = true;
         window.clearInterval(id);
      };
   }, [data.api.endpoint]);

   return (
      <RootLayout>
         <section className="pyxle-hero">
            <p className="pyxle-hero__eyebrow">{data.hero.eyebrow}</p>
            <h1>{data.hero.title}</h1>
            <p>v{data.hero.version}</p>
         </section>
         <section className="pyxle-section">
            <SectionLabel title="API pulse" description="pages/api/pulse.py" />
            {/* Command buttons, middleware snapshot, and API telemetry panels */}
         </section>
      </RootLayout>
   );
}
```

---

## 3. High-Level System Architecture

```
+-----------------+           +-------------------+
| Developer Shell |           |    Node Runtime   |
|  (pyxle CLI)    |           |  (Vite Dev Server)|
+--------+--------+           +---------+---------+
       |                              ^
       v                              |
+-----------------------+       +------+------+
| Pyxle Python Package  |       | transpiled |
| - CLI (Typer)         |       |  JSX pages |
| - Transpiler          |       +-------------+
| - DevServer Orchestr. |
| - Starlette App       |
+----------+------------+
         |
         v
   +--------------+
   | Starlette    |
   | App Server   |<----> Proxy <----> Vite (HMR, assets)
   +------+-------+
        |
        v
  pages/ (*.pyx & *.py)
```

---

## 4. Repository Layout & Convention

```
pyxle/
├── architecture.md
├── pyxle/
│   ├── __init__.py
│   ├── cli/
│   ├── compiler/
│   ├── devserver/
│   ├── routing/
│   ├── ssr/
│   └── templates/
├── tests/
├── tasks/
└── examples/
```

### Runtime Generated Structure

```
my-app/
├── pages/
│   ├── index.pyx
│   ├── components/
│   │   └── layout.jsx
│   └── api/pulse.py
├── middlewares/
│   └── telemetry.py
├── public/
│   ├── favicon.ico
│   ├── scripts/
│   │   └── pyxle-effects.js
│   └── styles/
│       └── pyxle.css
├── .pyxle-build/
│   ├── client/
│   │   ├── client-entry.js
│   │   └── pages/**/*.jsx
│   └── server/
│       └── pages/**/*.py
├── pyxle.config.json
├── package.json
└── requirements.txt
```

---

## 5. `.pyx` Intelligent Single-File Pipeline

1. **Read & Tokenize** – Compiler ingests `.pyx` content line-by-line.
2. **Mode Detection** – State machine switches between Python and JS/PSX:
   - Root-level `import`, `from`, `def`, `class`, `@` (or decorators) enter Python mode.
   - Indentation determines block extent; returning to root exits back to JS/PSX.
3. **Server Extraction** – Python sections are concatenated into `.pyxle-build/server/<route>.py`. The first `@server`-decorated async function becomes the loader.
4. **Client Extraction** – Remaining lines become `.pyxle-build/client/<route>.jsx`. The default export is the React component for SSR + hydration.
5. **Metadata Generation** – Compiler returns `(python_code, jsx_code, server_fn_name)` powering routing tables and SSR metadata.

### 5.1 Syntax rules enforced by the compiler

- **Section toggles**: Lines beginning with `# --- Python` or `# --- JavaScript/PSX` force the parser into the corresponding mode. Outside explicit toggles, heuristics inspect each line to decide whether it belongs to Python or JSX.
- **Heuristic fallbacks**: Root-level statements that look like Python (`def`, `async def`, `class`, `if/with/for/while`, decorators, imports without JS markers) flip the parser into Python mode. Lines that resemble JS (`export`, `const`, `<div>`, trailing semicolons, `await foo()` without colon) switch to JSX mode.
- **Indentation discipline**: The parser maintains an indentation stack; unexpected indents or dedents raise `CompilationError` with the offending line number. Blank lines inside Python blocks are tolerated, but misaligned returns or dedents are blocked early.
- **Loader detection**: Exactly one top-level `@server` **async** function is allowed. The function must be defined at module scope and take `request` as its first parameter. Violations surface precise errors (non-async, wrong argument name, nested definitions, or multiple loaders).
- **Tuple returns**: Loader bodies may return `(data, status_code)`; JSON metadata records the loader name/line while SSR will later interpret the status code.
- **Static pages**: When no Python code is present, the compiler emits a lightweight Python stub noting the page was generated by Pyxle and marks `loader_name=None` in metadata.
- **Consistency across platforms**: Input newlines are normalized (`\r\n` / `\r` → `\n`) before processing so Windows editors work seamlessly with POSIX tooling.
- **Generated artifact layout**: Server modules land in `.pyxle-build/server/pages/...`, client JSX under `.pyxle-build/client/pages/...`, and page metadata under `.pyxle-build/metadata/pages/...` with JSON payloads describing route path, loader, and artifact pointers.
- **Manual invocations**: `pyxle compile <path/to/page.pyx>` (hidden CLI command) runs the same pipeline, reporting the paths of generated artifacts. This is useful prior to having the dev server orchestrate incremental builds.

### Server Loader Contract

- `async` function with first argument `request: starlette.requests.Request`.
- Return `dict` (implies `200`) or `(dict, status_code)`.
- The compiler injects `from pyxle.runtime import server` when a loader is detected, so authors can rely on `@server` without adding imports manually (custom decorators can still be provided explicitly).
- Violations surface precise, user-facing errors.

### Example: Dynamic Route (`pages/posts/[id].pyx`)

```python

import httpx

@server
async def get_post_data(request):
   post_id = request.params.get("id")
   try:
      async with httpx.AsyncClient() as client:
         response = await client.get(
            f"https://jsonplaceholder.typicode.com/posts/{post_id}"
         )
         response.raise_for_status()
         return response.json()
   except httpx.HTTPStatusError as exc:
      if exc.response.status_code == 404:
         return {"error": "Post not found", "id": post_id}, 404
      return {"error": str(exc)}, 500

# --- JavaScript/PSX (Client + Server for SSR) ---
import React from 'react';

export default function PostPage({ data }) {
   if (data.error) {
      return (
         <div>
            <h1>An Error Occurred</h1>
            <p>{data.error}</p>
            {data.id && <p>Could not find post with ID: {data.id}</p>}
         </div>
      );
   }

   return (
      <article>
         <h1>{data.title} (Post #{data.id})</h1>
         <p>{data.body}</p>
         <a href="/">Go Home</a>
      </article>
   );
}
```

### Example: Static Page (`pages/about.pyx`)

```javascript
// --- JavaScript Only ---
import React from 'react';

export default function AboutPage({ data }) {
   return (
      <div>
         <h1>About Us</h1>
         <p>We are building Pyxle!</p>
      </div>
   );
}
```

### 5.2 Advanced Route Segments

Pyxle now mirrors the richer routing semantics developers expect from frameworks like Next.js:

- **Route groups** – Directory names wrapped in parentheses (for example `(marketing)/about.pyx`) organize files without changing the resulting URL. Only non-parenthesized segments participate in the public path.
- **Catch-all segments** – Files named `pages/docs/[...slug].pyx` expand to `/docs/{slug:path}` when converted to Starlette routes, allowing arbitrarily deep sub-paths to resolve to the same page or API endpoint.
- **Optional catch-all segments** – `[[...slug]].pyx` registers both the base route (e.g. `/docs`) and the `/{slug:path}` alias so `/docs` and `/docs/foo/bar` share the same handler. The compiler emits `alternate_route_paths` metadata, which the dev server and manifest builder consume to mount every alias explicitly.

The same rules apply inside `pages/api/`, so both page and API routes benefit from groups and catch-all resolution without extra configuration.

---

## 6. API Route Specification (`pages/**/*.py`)

Any `.py` file in `pages/` (commonly under `pages/api/`) becomes an API endpoint. Future configuration will allow redefining the API mount path or treating any `.py` without a paired `.pyx` as an API route automatically.

### Example: Function Endpoint (`pages/api/pulse.py`)

```python
from __future__ import annotations

import os
import platform
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import JSONResponse

from pyxle import __version__

_START_TIME = datetime.now(tz=timezone.utc)


def build_pulse_payload() -> dict[str, object]:
   now = datetime.now(tz=timezone.utc)
   uptime = now - _START_TIME
   return {
      "timestamp": now.isoformat(),
      "uptime": str(uptime).split('.')[0],
      "pyxleVersion": __version__,
      "python": platform.python_version(),
      "hostname": platform.node(),
      "pid": os.getpid(),
      "features": [
         "Single-file loader + component authoring",
         "Starlette-compatible API routes",
         "Project-scoped middleware via pyxle.config.json",
         "Vite-powered client bundling",
      ],
   }


def _request_details(request: Request) -> dict[str, str]:
   client = request.client[0] if request.client else "unknown"
   return {
      "path": request.url.path,
      "client": client,
      "method": request.method,
      "userAgent": request.headers.get("user-agent", "unknown"),
   }


async def endpoint(request: Request) -> JSONResponse:
   payload = build_pulse_payload()
   payload["request"] = _request_details(request)
   return JSONResponse(payload)
```

### Example: Class Endpoint (`pages/api/users.py`)

```python
from starlette.responses import JSONResponse
from starlette.endpoints import HTTPEndpoint

class UserEndpoint(HTTPEndpoint):
   async def get(self, request):
      return JSONResponse([{"id": 1, "name": "Alice"}])

   async def post(self, request):
      data = await request.json()
      return JSONResponse({"message": "User created", "data": data}, status_code=201)
```

### Example: Dynamic Route (`pages/api/users/[id].py`)

```python
from starlette.responses import JSONResponse
from starlette.endpoints import HTTPEndpoint

class UserDetailEndpoint(HTTPEndpoint):
   async def get(self, request):
      user_id = request.params.get("id")
      return JSONResponse({"id": user_id, "name": "Alice"})

   async def put(self, request):
      user_id = request.params.get("id")
      data = await request.json()
      return JSONResponse({"id": user_id, "name": data.get("name")})
```

---

## 7. CLI Commands

### `pyxle init <name>`

- Create project directory structure (`pages/`, `pages/api/`, `public/`).
- Scaffold starter files:
   - `pages/index.pyx` (dark-mode dashboard using loaders + middleware).
   - `pages/components/layout.jsx` helpers and `pages/api/pulse.py` diagnostics endpoint.
   - `public/styles/pyxle.css`, `public/scripts/pyxle-effects.js`, and favicon.
   - `middlewares/telemetry.py` plus `pyxle.config.json` registering it by default.
   - `package.json`, `requirements.txt`, `.gitignore`.
- Enforce template utilities only when roadmap tasks require them.

### `pyxle install`

- Runs `python -m pip install -r requirements.txt` and `npm install` inside the provided directory.
- Accepts `--no-python` or `--no-node` to skip either installer when you want to manage dependencies yourself.
- `pyxle init <name> --install` calls the same workflow automatically after scaffolding.

### `pyxle dev`

1. Ensure `.pyxle-build/` exists, cleaning stale artifacts.
2. Transpile `.pyx` files and copy `.py` API modules into build cache.
3. Generate Vite bootstrap files (`vite.config.js`, `client-entry.js`).
4. Launch Vite: `vite dev --config .pyxle-build/client/vite.config.js --port 5173`.
5. Build Starlette ASGI app; run via Uvicorn on `localhost:8000`.
6. Watch `pages/` + `public/` with watchdog; debounce rebuilds and invalidate import caches.

Command options:

- `--host` / `--port` — customise the Starlette bind address.
- `--vite-host` / `--vite-port` — coordinate the proxied Vite development server.
- `--debug` / `--no-debug` — toggle debug behaviours (logging, overlay hooks).
- `--log-format` — pick `console` (emoji/text) or `json` output for observability pipelines.

---

## 8. Transpiler Internals

- `python_lines`, `jsx_lines`, `server_fn_name` tracked per file.
- Root-level Python triggers Python mode; indentation maintains context.
- `@server` decorator detection captures next `def` for loader name.
- Returns `(python_code, jsx_code, server_fn_name)`; metadata stored for routing.
- Future extensions: improved indentation heuristics, brace-aware JSX parsing, plugin hooks.

---

## 9. Dev Server Lifecycle (`pyxle dev`)

1. **Initialization**
   - `DevServerSettings.from_project_root()` resolves canonical paths, ports, debounce windows, and feature flags for the session.
   - `ensure_fresh_build_cache()` compares the cached `meta.json` schema version, removing incompatible artifacts before work begins.
   - `initialize_build_directories()` guarantees `.pyxle-build/` exposes `client/pages/`, `server/pages/`, and `metadata/` roots before any compilation occurs.
   - `build_once(..., force_rebuild=True)` performs a clean pass to compile every page, copy API modules, prune removed artifacts, and return a `BuildSummary` used for launch logs.
   - `write_client_bootstrap_files()` emits deterministic `vite.config.js`, `client-entry.js`, and `tsconfig.json` into `.pyxle-build/client/`, ensuring Vite and the browser hydration entry always reflect the latest settings.
   - `_ensure_vite_port_available()` checks whether the preferred Vite port is already bound and increments until a free slot is found, warning the user when falling back to a new port.

2. **Transpile**
   - `scan_source_tree()` walks `pages/` to enumerate `.pyx` pages and API modules with content hashes for incremental builds.
   - `build_once()` compiles changed `.pyx` files, copies updated API modules, and prunes artifacts for removed sources while refreshing `meta.json` hashes.
      - `build_metadata_registry()` assembles page + API descriptors (routes, artifact paths, loader info) from cached metadata for the Starlette app.
        - `build_route_table()` converts registry entries into Starlette-ready route descriptors, translating `[segment]` syntax into `{segment}` automatically.
   - For each `.pyx`, run compiler and persist to `server/` + `client/`.
   - Copy `.py` API files into `.pyxle-build/server/` with relative structure.

3. **Launch Vite**
   - `ViteProcess` builds the command (`vite dev --config .pyxle-build/client/vite.config.js --port <port>` by default) and spawns it as an asyncio subprocess.
   - Stdout/stderr streams are piped through the shared `ConsoleLogger`, so terminal output mirrors native Vite logs without breaking Typer formatting.
   - A readiness probe repeatedly attempts a TCP connection to the Vite host/port; startup blocks until the probe succeeds or times out, surfacing actionable errors when the process exits prematurely. Shutdown sends `SIGTERM`, escalating to `SIGKILL` only if the process refuses to exit.

4. **Start Starlette / Uvicorn**
    - `build_metadata_registry()` materialises the route registry from cached metadata, and `build_route_table()` converts it to Starlette routes (pages + API endpoints) with dynamic `[param]` segments translated to `{param}`.
    - `create_starlette_app()` wires routing, static file handling, and the Vite proxy middleware that forwards asset requests; `uvicorn.Server` hosts it on the configured host/port (`loop="asyncio"`, `reload=False`, log config suppressed so Typer colours survive).
   - Default route policies attach `RouteContext` metadata to `request.scope["pyxle"]` and guard API verbs; additional async hooks supplied via `routeMiddleware.pages` / `routeMiddleware.apis` run per route before handlers execute, so auth/rate-limit logic can introspect source paths, loader presence, and hashed artifact IDs without global middleware gymnastics.
    - The Starlette app exposes `/healthz` (liveness) and `/readyz` (503 until Vite + watcher startup completes) so orchestrators can perform structured health checks.
    - `DevServer.start()` announces both Starlette and Vite URLs, then enters `uvicorn.Server.serve()` while holding references to the watcher and Vite process for coordinated shutdown.

5. **Watch & Rebuild**
   - Watchdog observers track `pages/` and `public/`, feeding events through a debounced buffer so rapid edits collapse into a single rebuild.
   - `ProjectWatcher` logs affected paths, calls `build_once(..., force_rebuild=False)` for incremental compilation, and retains the latest statistics for overlays/health checks.
   - Incremental builds refresh metadata and artifacts; Vite sees updated client bundles instantly because it serves straight from `.pyxle-build/client/`.

---

## 10. SSR & Hydration Flow

1. **Request Handling** – Starlette matches incoming path to page route, resolving dynamic params.
2. **Data Fetch** – Loader invoked with `request`; may return `(props, status)`.
3. **SSR Rendering**
   - Load transpiled server module via `importlib`.
   - Resolve the internal `ComponentRenderer` (or a custom factory) to transform props into an HTML placeholder that the client hydrates.
   - Generate HTML string for `<div id="root">`; if loader or renderers explode, fall back to the developer error document to keep Vite attached.

4. **Template Injection**

```python
data_json = json.dumps(props)
page_glob_path = "/pages/posts/[id].jsx"  # example

html = f"""<!DOCTYPE html>
<html>
  <head>
   <title>Pyxle App</title>
   <script type="module" src="http://localhost:5173/@vite/client"></script>
  </head>
  <body>
   <div id="root">{rendered_html}</div>
   <script id="__PYXLE_PROPS__" type="application/json">{data_json}</script>
   <script>window.__PYXLE_PAGE_PATH__ = "{page_glob_path}";</script>
   <script type="module" src="http://localhost:5173/client-entry.js"></script>
  </body>
</html>"""
```

Fallback renders reuse the same Vite client attachment but omit the hydration bundle so developers immediately see descriptive loader errors in the browser.

5. **Client Hydration (`client-entry.js`)**

```javascript
import React from 'react';
import ReactDOM from 'react-dom/client';

const pages = import.meta.glob('/pages/**/*.jsx');

(async () => {
   const props = JSON.parse(
      document.getElementById('__PYXLE_PROPS__').textContent || '{}'
   );
   const pagePath = window.__PYXLE_PAGE_PATH__;
   const moduleLoader = pages[pagePath];

   if (!moduleLoader) {
      console.error(`[Pyxle] Failed to hydrate: ${pagePath} not found`);
      return;
   }

   const PageComponent = (await moduleLoader()).default;
   ReactDOM.hydrateRoot(
      document.getElementById('root'),
      <PageComponent {...props} />
   );
})();
```

---

## 11. Vite Proxy & Networking

- Asset requests (`/@vite/*`, `/*.js`, `/*.css`, `/*.map`) proxied via shared `httpx.AsyncClient`.
- Middleware uses `ViteProxy` to stream responses directly from Vite while filtering hop-by-hop headers and reusing a shared `httpx.AsyncClient`.
- Public assets served with `Starlette.StaticFiles`.
- Proxy logs 4xx/5xx responses for visibility and returns informative `502` errors when Vite is unreachable; process isolation ensures graceful restarts on Vite exit.

---

## 12. Configuration & Extensibility

- **Project Configuration** – `pyxle.config.json` lives at the project root and is loaded automatically by `pyxle dev`. Supported keys:
   - `pagesDir`, `publicDir`, `buildDir` (relative paths)
   - `starlette` and `vite` objects with `host` + `port`
   - `debug` boolean toggle for overlay/log behaviour
   - `middleware` array containing `"module:attribute"` specs; modules are resolved relative to the project root after Pyxle prepends the root to `sys.path`, and attributes can be `BaseHTTPMiddleware` subclasses, ready-made `starlette.middleware.Middleware` objects, or factories that return either form.
   Unknown keys or invalid types raise a `ConfigError` early, keeping failures actionable.
- **Merged Overrides** – CLI options (`--host`, `--port`, `--vite-host`, `--vite-port`, `--debug/--no-debug`) override matching config values only when supplied. `--config` selects an alternate file, and `--print-config` pretty-prints the merged result before startup for quick auditing.
- **Environment Overrides** – Planned `PYXLE_` prefixed variables (e.g., `PYXLE_VITE_PORT`) will layer on after config files.
- **Plugin Hooks (Future)** – Extensible points for custom loaders, renderers, CLI commands without complicating MVP pathways.

---

## 13. Observability & Error Handling

- Structured logging for CLI and dev server (`INFO`, `WARNING`, `ERROR`).
- Loader exceptions produce developer-friendly overlays (Phase 5).
- Overlay payloads now ship loader/renderer/hydration breadcrumbs, and the
   client hydration bootstrap raises the same UI when the browser throws before
   mounting the React tree.
- Planned `pyxle doctor` command for dependency health.
- SSR errors surfaced with meaningful status codes and JSON/HTML responses.

---

## 14. Quality & Testing Strategy

Pyxle enforces **≥95% coverage** across Python and JavaScript.

| Layer               | Scope                                                      | Tooling                                         |
|---------------------|------------------------------------------------------------|-------------------------------------------------|
| Unit Tests (Python) | Compiler state machine, CLI, routing helpers               | `pytest`, `pytest-asyncio`, `coverage.py`       |
| Integration Tests   | CLI E2E (scaffold, dev run), SSR pipeline                  | `pytest`, `anyio`, temp dirs, mocks             |
| Contract Tests      | `.pyx` → SSR output invariants                             | Golden files / snapshot comparisons             |
| JS Unit Tests       | `client-entry.js` logic, hydration utils                   | `vitest`                                        |
| E2E Smoke           | Launch dev server, HTTP assertions                         | `pytest`, `httpx.AsyncClient` or Playwright     |

- `coverage.py` configured with `fail_under = 95`.
- CI pipeline: lint → tests → smoke → coverage gate → artifacts.
- Fixtures include temporary scaffolds via `pyxle init`, mocked Vite subprocess, Starlette `TestClient`.

---

## 15. Security & Performance

- Monitor Vite subprocess; restart on failure.
- Debounce file events, invalidate import caches to avoid stale modules.
- Config-driven middleware hooks can inject auth, rate limiting, or observability layers without forking the server.
- Memoize transpilation outputs; reuse loader modules when possible.
- Vite handles bundling, tree shaking, code splitting for future `pyxle build`.

---

## 16. Development Roadmap

- **Stage 1: CLI & Scaffolding**
   - [ ] 1.1 Setup Python project, Typer CLI entrypoint.
   - [ ] 1.2 Implement `pyxle init <name>` per scaffolding spec.
- **Stage 2: Transpiler**
   - [ ] 2.1 Create `compiler.py`.
   - [ ] 2.2 Implement Python vs. JS/PSX state machine.
   - [ ] 2.3 Detect `@server` loader name.
   - [ ] 2.4 Author unit tests (≥5 `.pyx` scenarios).
- **Stage 3: Dev Server Core**
   - [ ] 3.1 Implement `pyxle dev`.
   - [ ] 3.2 Add watchdog for `pages/`.
   - [ ] 3.3 Persist transpiled outputs to `.pyxle-build/`.
   - [ ] 3.4 Wire Starlette routes for pages + APIs.
   - [ ] 3.5 Finalize API endpoint handler detection.
- **Stage 4: Vite & SSR**
   - [ ] 4.1 Spawn Vite subprocess.
   - [ ] 4.2 Implement Vite proxy middleware.
   - [ ] 4.3 Build `ssr_handler`.
   - [ ] 4.4 Implement built-in component renderer (pluggable runtime).
   - [ ] 4.5 Inject HTML template (props, page path, scripts).
   - [ ] 4.6 Write `client-entry.js` hydration logic.
- **Stage 5: Error Handling & Polish (Post-MVP)**
   - [ ] Developer error overlay, enhanced diagnostics.
   - [ ] `pyxle build` production pipeline.
- **Stage 6: MVP (v0.1 – v0.3)**
   - [ ] Finalize middleware hooks for pages and APIs, including route metadata introspection, default policies, and hardened overlay messaging.
   - [ ] Document and scaffold shared layout primitives (`Link`, `Head`, root layout), Tailwind CSS integration, and the end-to-end `pyxle init` → `pyxle dev` walkthrough.
   - [ ] Lock in coverage targets, security baselines (CSP nonce path), and production deployment guidance for the public preview.
- **Stage 7: Developer Preview (v0.4 – v0.6)**
   - [ ] Deliver advanced routing (route groups, optional catch-all), nested templates, and streaming SSR with Suspense-style loaders and revalidation hooks.
   - [ ] Stand up the expanded data layer (RPC/actions, dependency injection), global styling/image utilities, and production `pyxle build` with incremental outputs.
   - [ ] Broaden DX tooling: code splitting analysis, snippet generators, `.env` loading, static type-checking, test harness upgrades, and baseline security middleware.
- **Stage 8: Stable (v0.7 – v1.0)**
   - [ ] Launch plugin and theme APIs with a registry, SSR caching + prefetch primitives, and edge/serverless adapters with distributed cache coordination.
   - [ ] Deepen observability (integrations, `/healthz`/`/readyz`), QA automation, and internationalization/SEO/accessibility tooling.
   - [ ] Harden security posture and roll out client/server state primitives with richer developer tooling (docs CLI, bundle analyzer UI, changelog automation).
   - [ ] Finalize enterprise tooling: template registry, docs CLI, changelog generator, Playwright E2E, and polished deployment workflows leading to v1.0.

---

## 17. Collaboration Rituals

- Update `roadmap.md` for every change set (checkbox progress).
- Keep `memory.md` current with decisions, shortcuts, unscheduled TODOs.
- Document new commands/flags in relevant phase README and reference here when workflows shift.
- Prefer tests-first development aligned with roadmap acceptance criteria.

---

For granular execution steps and milestone planning, consult the `tasks/` directory accompanying this architecture.
