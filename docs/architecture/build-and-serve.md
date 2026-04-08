# Build and serve

`pyxle dev` is what you run during development. `pyxle build` and
`pyxle serve` are what you run for production. They share most of
their code with the dev server but make a few important changes:

| Aspect | `pyxle dev` | `pyxle build` + `pyxle serve` |
|---|---|---|
| Vite | dev server on :5173 | one-time bundle, then no Vite |
| Source compilation | incremental on file change | full rebuild, all at once |
| File watcher | running | not running |
| HMR / React Refresh | enabled | disabled |
| Module reloading | per-request `sys.modules` purge | imported once at startup |
| Error responses | full stack trace + dev overlay | generic `Server Error` |
| Asset serving | proxy to Vite | static files from `dist/client/` |
| Route discovery | metadata files in `.pyxle-build/` | `dist/page-manifest.json` |
| Port | 8000 by default | 8000 by default |

This doc explains the production pipeline: what `pyxle build` does,
what artifacts it produces, and how `pyxle serve` runs them.

**Files (`pyxle/build/`):**

| File | Lines | What it does |
|---|---|---|
| `pipeline.py` | 343 | The `run_build()` orchestrator |
| `vite.py` | 193 | Invokes `vite build` and parses its output |
| `manifest.py` | 26 | Loads `dist/page-manifest.json` |
| `__init__.py` | 7 | Re-exports |

The CLI commands themselves live in `pyxle/cli/__init__.py`:
`build` is around line 400, `serve` is around line 517.

---

## What `pyxle build` actually does

When you run `pyxle build`, the pipeline executes six steps in order:

```
1. Compile every .pyx file to artifacts in .pyxle-build/
   (same as `pyxle dev`'s initial build)
   │
   ▼
2. Run `npm run build` (or `vite build` directly)
   - esbuild transforms JSX to JS
   - Vite bundles, code-splits, and hashes assets
   - Output goes to .pyxle-build/dist/ (Vite's output)
   │
   ▼
3. Read .pyxle-build/dist/.vite/manifest.json
   (Vite's mapping from source files to hashed bundle entries)
   │
   ▼
4. Build dist/page-manifest.json
   - For each page, find the bundled JS + CSS chunk(s)
   - Walk the import graph to collect transitively-required CSS
   - Resolve aliases (e.g., optional catch-all routes)
   │
   ▼
5. Copy artifacts into dist/
   - dist/server/   ← compiled .py loaders
   - dist/metadata/ ← compiled .json metadata
   - dist/client/   ← Vite's bundled JS/CSS (hashed)
   - dist/public/   ← static files from public/
   - dist/page-manifest.json
   │
   ▼
6. Print a summary
   "✅ Build completed — 19 page(s), 1 API module(s), 5 asset(s)"
```

Source: `build/pipeline.py:35-86`.

The `dist/` directory is the **only thing your deployment needs**.
Once it exists, you can `pyxle serve` it on a server, copy it to a
container image, push it to a CDN, or do anything else you'd do with
a static-plus-server build.

---

## Step 1: Compile sources

Steps 1 of `pyxle build` is identical to the initial build of `pyxle
dev` — same `build_once()` function, same `compile_file()` calls, same
`.pyxle-build/` layout. The compiler doesn't know or care that we're
in production mode; it just produces artifacts.

The result is the same three files per page in `.pyxle-build/`:

```
.pyxle-build/
├── server/pages/index.py
├── client/pages/index.jsx
└── metadata/pages/index.json
```

Plus any layout-composed route modules in
`.pyxle-build/client/routes/` and any `pages/api/*.py` files copied
to `.pyxle-build/server/api/`.

If anything fails to compile (a parser error, an unresolved import,
a missing decorator, etc.), the build aborts here and prints the
error. Production builds are **strict** — there is no tolerant mode
for `pyxle build`. The first error stops everything.

---

## Step 2: Run Vite build

`run_vite_build()` (`build/vite.py:20-76`) invokes Vite to bundle the
client-side JavaScript. It tries multiple invocation strategies in
order:

1. **`npm run build`** if `package.json` has a `build` script.
2. **Local `node_modules/.bin/vite build`** if installed.
3. **`node node_modules/vite/bin/vite.js build`** as a fallback.
4. **`npx vite build`** if no local install.

Each candidate is validated with `--version` before use. If no Vite
is available at all, the pipeline runs `npm install` to restore
dependencies, then retries.

The Vite invocation passes:

- `--config .pyxle-build/client/vite.config.js` — Pyxle's
  auto-generated Vite config
- `--manifest` — produce a manifest JSON that maps source files to
  hashed bundle entries
- `PYXLE_VITE_BASE=/client/dist/` env var — sets the asset base path
  so Vite emits URLs like `/client/dist/assets/index-abc123.js`
  instead of `/assets/index-abc123.js`

Vite's output:

- `.pyxle-build/dist/.vite/manifest.json` — the manifest
- `.pyxle-build/dist/assets/*.js` — bundled, code-split, hashed JS
- `.pyxle-build/dist/assets/*.css` — bundled, hashed CSS
- `.pyxle-build/dist/index.html` — Vite's default HTML output (we
  ignore this; Pyxle generates its own HTML at request time)

Vite logs are streamed to the console with a `[vite]` prefix. If the
exit code is non-zero, Pyxle raises `ViteBuildError` with the captured
stderr.

---

## Step 3: Load Vite's manifest

Vite's manifest looks like this:

```json
{
  "pages/index.jsx": {
    "file": "assets/index-abc123.js",
    "isEntry": true,
    "imports": ["_shared-def456.js"],
    "css": ["assets/index-789xyz.css"]
  },
  "_shared-def456.js": {
    "file": "assets/shared-def456.js",
    "imports": [],
    "css": ["assets/shared-ghi789.css"]
  },
  "pages/about.jsx": {
    "file": "assets/about-jkl012.js",
    "isEntry": true,
    "imports": ["_shared-def456.js"],
    "css": []
  }
}
```

Each entry tells you the **bundled file path**, the **list of
imported chunks** (so you can preload them), and the **direct CSS
dependencies**.

The interesting part is the import chain. `pages/index.jsx` imports
`_shared-def456.js`, which itself has CSS. To get the **complete CSS
list** for `index.jsx`, we need to walk the imports recursively and
collect all `css` arrays. Otherwise we'd ship pages with missing
styles from shared modules.

`_collect_css_assets()` (`build/pipeline.py:211-259`) does this walk.
It uses a visited set to handle cycles (Vite shouldn't produce
cycles, but defense in depth) and returns the deduplicated list of
CSS files for each entry.

---

## Step 4: Build the page manifest

Vite's manifest is keyed by source file. Pyxle's `page-manifest.json`
is keyed by **route**:

```json
{
  "/": {
    "client": {
      "file": "client/dist/assets/index-abc123.js",
      "css": ["client/dist/assets/index-789xyz.css", "client/dist/assets/shared-ghi789.css"]
    },
    "server": {
      "file": "server/pages/index.py",
      "module_key": "pyxle.server.pages.index",
      "loader_name": "load_home"
    },
    "metadata": "metadata/pages/index.json"
  },
  "/about": {
    ...
  },
  "/posts/{id}": {
    ...
  }
}
```

`_build_page_manifest()` (`build/pipeline.py:262-325`) iterates the
metadata registry, looks up each page's bundled assets in the Vite
manifest, walks the import chain to collect CSS, and emits one entry
per route.

Aliases (from `[[...slug]].pyx` optional catch-alls) get their own
entry pointing at the same data:

```json
{
  "/shop/{path:path}": { /* primary */ },
  "/shop": { /* alias — same data */ }
}
```

The page manifest is written to `dist/page-manifest.json` and is the
**source of truth for production routing**. The dev server's metadata
registry is built from `.pyxle-build/metadata/*.json`; the production
server's metadata registry is built from this single file.

---

## Step 5: Copy into `dist/`

The final layout under `dist/` is:

```
dist/
├── server/                      ← compiled Python loaders
│   ├── pages/
│   │   ├── index.py
│   │   ├── about.py
│   │   └── posts/[id].py
│   └── api/
│       └── health.py
│
├── client/                      ← bundled JS + CSS for the browser
│   └── dist/
│       └── assets/
│           ├── index-abc123.js
│           ├── shared-def456.js
│           ├── index-789xyz.css
│           └── shared-ghi789.css
│
├── metadata/                    ← compiled .json metadata (one per page)
│   └── pages/
│       ├── index.json
│       └── ...
│
├── public/                      ← static files copied from public/
│   ├── favicon.ico
│   └── ...
│
└── page-manifest.json           ← the route → assets mapping
```

The `dist/server/` and `dist/metadata/` directories are direct copies
of `.pyxle-build/server/` and `.pyxle-build/metadata/`. The
`dist/client/dist/` directory is Vite's output (`.pyxle-build/dist/`)
copied verbatim.

`dist/public/` is a copy of your project's `public/` directory (if
it exists). These are static assets that ship to the browser
unchanged: favicons, images, robots.txt, etc.

The double `dist/client/dist/` nesting is intentional — Vite's output
naturally lives under a `dist/` subdirectory of its base path, and
Pyxle preserves that. The serving layer is configured to mount it at
the right URL prefix (`/client/dist/...`).

---

## What `pyxle serve` does

Once you have a `dist/` directory, `pyxle serve` runs it. The serve
command:

1. **Loads `pyxle.config.json`** with `debug=False`. This is the
   single most important setting that flips the framework into
   production mode.
2. **Loads `dist/page-manifest.json`** as the route source.
3. **Builds a `MetadataRegistry`** from the manifest entries.
4. **Creates a `RouteTable`** from the registry.
5. **Spawns the SSR worker pool.** Same code as dev mode.
6. **Builds a Starlette app** with the same `create_starlette_app()`
   factory. The factory checks `settings.debug` and includes the
   `GZipMiddleware` (production-only) and skips the Vite proxy
   middleware (which would have nothing to talk to).
7. **Runs uvicorn** to serve the Starlette app.

Source: `cli/__init__.py:517-733`.

The result is a process that:

- Listens on port 8000 (or whatever `--port` you pass).
- Imports each compiled `.py` module **once at startup**, not per-request.
- Serves `dist/client/`, `dist/public/`, and `dist/server/api/*.py`
  routes via `StaticFiles` mounts.
- Handles page routes the same way `pyxle dev` does — same SSR
  pipeline, same loader execution, same component rendering, same
  head merging.
- Responds to errors with **opaque** generic pages instead of the
  developer overlay.

### Why is the SSR worker pool the same in production?

Because the rendering work doesn't change between dev and prod. The
React component is the same JavaScript. esbuild bundles it the same
way. `renderToString` produces the same output. The cost of running
React on the server is identical.

The only thing that changes is *how often* you pay for it: in dev,
the worker is mostly idle and serves your single-developer requests.
In production, the worker pool needs to scale to handle real
traffic — which is why the recommended worker count for production
is *the number of CPU cores*, not 1.

You can adjust:

```bash
pyxle serve --ssr-workers 4
```

…to spin up four persistent Node.js workers. Round-robin dispatch
gives you four-way SSR parallelism within one Pyxle process.

### Stateless processes, scale horizontally

Pyxle's serve process is **stateless**: nothing is stored
in-process between requests. This means you can run multiple Pyxle
instances behind a load balancer and they'll all serve the same
content. The scaling story is "run more processes" — not "run more
threads" or "tune a connection pool."

---

## Configuration overrides for production

`pyxle serve` builds the production config with three overrides:

```python
production_config = file_config.apply_overrides(
    debug=False,
    starlette_host=host,
    starlette_port=port,
)
```

Source: `cli/__init__.py:598-602`.

`debug=False` is the critical one. It turns off:

- The hot-reload `sys.modules` purge
- The dev error overlay (replaced with opaque generic responses)
- The Vite client tag in the document `<head>`
- The React Refresh preamble
- The WebSocket overlay endpoint

It also turns *on*:

- GZip middleware
- Production asset path resolution via `dist/page-manifest.json`
- Streaming responses use the production document shell

The full list of what `debug` controls is scattered across
`devserver/`, `ssr/`, and `build/` — search the codebase for
`settings.debug` to see every gate.

### Other CLI flags for `serve`

- **`--port 8000`** — bind port (default 8000)
- **`--host 0.0.0.0`** — bind host (default 127.0.0.1; use 0.0.0.0
  for "listen on all interfaces", which you'll want behind a
  reverse proxy)
- **`--dist-dir ./dist`** — where to read the build output from
  (default: `./dist` in the current directory)
- **`--skip-build`** — skip the implicit `pyxle build` and use the
  existing `dist/` as-is. Useful when the build artifacts come
  from CI and you just want to run them.
- **`--no-skip-build`** — force a fresh build before serving (the
  default)
- **`--serve-static / --no-serve-static`** — whether to serve
  `dist/client/` and `dist/public/` directly. Disable this if you're
  putting Pyxle behind a CDN that handles static assets.
- **`--ssr-workers N`** — number of persistent Node.js workers
  (default 1)

---

## What's in a deployable artifact?

If you want to deploy a Pyxle app, the artifact is the `dist/`
directory plus the Python source for any files outside `pages/`
(your shared utilities, your dependencies, your `pyxle.config.json`).

A typical deployment looks like:

```
my-app/
├── dist/                        ← from pyxle build
├── pyxle.config.json
├── requirements.txt             ← pinned Python deps
├── pyproject.toml
└── public/                      ← optional, if not already in dist/
```

The deployment process:

1. **On the build machine:** `pip install -r requirements.txt && npm
   install && pyxle build`
2. **Copy `dist/`, `pyxle.config.json`, and the Python source** to
   the server (or build a container image).
3. **On the server:** `pip install -r requirements.txt`. Node.js
   isn't required for *serving* unless you have SSR workers
   spawning... wait, scratch that. Node.js **is** required — the
   SSR pipeline runs React on Node.js workers. You need Node.js on
   the production server too.
4. **Run** `pyxle serve --port 8000 --host 0.0.0.0`.
5. **Put it behind a reverse proxy** (nginx, Caddy, Cloudflare, ALB,
   whatever you like). Pyxle doesn't try to be a frontend proxy
   itself.

The `pyxle-dev` deployment (the marketing site) is a working
example: it builds in CI, deploys to an EC2 instance, and serves
behind nginx with TLS termination. It uses `pyxle serve --ssr-workers
2` because the box has 2 vCPUs.

---

## Why a separate build step?

You might wonder: why do `pyxle build` and `pyxle serve` exist as
separate commands? Why not just have `pyxle serve` build on demand,
or `pyxle dev` run in production mode?

Three reasons:

1. **Build is slow, serve is fast.** `pyxle build` takes 10-60
   seconds for a typical project (mostly Vite). `pyxle serve` takes
   under a second to come up. You don't want to rebuild every time
   you restart the server in CI. Separating the two lets you bake
   `dist/` into a container image and start instances quickly.

2. **Build needs the dev tools, serve doesn't.** `pyxle build`
   requires Node.js, npm, Vite, esbuild, and the JSX parser. `pyxle
   serve` only requires Python + Node.js for the SSR worker. You
   can ship a much smaller production runtime by not including
   the build toolchain.

3. **The dev server's incremental builder doesn't apply.** It's
   optimized for "one file changed, recompile only that one." A
   production build is the opposite — *everything* needs to be
   compiled at once, with full bundle optimization. Different code
   path, different concerns.

The separation also makes the framework easier to reason about:
"build" = "produce artifacts", "serve" = "consume artifacts". Each
verb has a clear input and output.

---

## Where to read next

- **[The CLI](cli.md)** — How `pyxle build` and `pyxle serve` parse
  their flags, apply config overrides, and bridge user input to the
  build pipeline.

- **[Server-side rendering](ssr.md)** — How the SSR pipeline serves
  pages in production mode (which is the same code as dev mode,
  with `debug=False`).

- **[The dev server](dev-server.md)** — The dev counterpart to
  `pyxle serve`. Shares most of its code with the production
  serving stack, but adds the file watcher, the Vite proxy, and the
  hot-reload mechanism.
