# Pyxle

Pyxle is a Python-first full-stack framework that pairs a Typer-powered CLI with Starlette, Vite, and React to deliver a Next.js-style developer experience. The MVP currently focuses on the project scaffolding workflow.

## Quick Start

```bash
# Create a new Pyxle project (add --install to run pip + npm automatically)
pyxle init my-awesome-app

cd my-awesome-app

# Install dependencies via the bundled helper
pyxle install

# Launch the development server (Phase 2+)
pyxle dev
```

The scaffold ships a ready-to-use telemetry middleware via `pyxle.config.json`, dark-mode styles under `public/styles/pyxle.css`, and a tiny `public/scripts/pyxle-effects.js` helper so the `.pyx` page stays focused on Python + React behavior instead of inline CSS/JS. The default project now includes three ready-to-edit routes (overview, projects, diagnostics) so you can immediately explore loaders, middleware, and API wiring.

Prefer a narrative version? Follow the step-by-step guide in
[`docs/walkthrough.md`](docs/walkthrough.md) to see the CLI, compiler, and dev
server working together with screenshots and overlay tips.

## Available Commands

- `pyxle init <name>` — Scaffold a new project with starter pages, API route, and configuration files.
- `pyxle init <name> --force` — Overwrite an existing directory.
- `pyxle init <name> --install` — Scaffold and immediately install Python + Node dependencies.
- `pyxle init <name> --template <template>` — Placeholder for future template variants (only `default` is currently accepted).
- `pyxle install [path]` — Runs `python -m pip install -r requirements.txt` and `npm install` (use `--no-python` / `--no-node` to skip either step).
- `pyxle serve [path] --dist-dir <dir>` — Boot the production Starlette app without Vite. Runs `pyxle build` by default, then serves the contents of `dist/` via Uvicorn (add `--skip-build` when you only want to reuse existing artifacts). Disable the built-in static mounts with `--no-serve-static` if a CDN or edge proxy owns your asset hosting.

## Custom middleware hooks

Projects can inject Starlette-compatible middleware globally via `pyxle.config.json`:

```jsonc
{
	"middleware": [
		"middlewares.telemetry:PyxleTelemetryMiddleware"
	]
}
```

Each entry follows the `"module:attribute"` pattern. The module is resolved relative to the project root, so you can store middleware alongside your pages:

```python
# middlewares/telemetry.py
import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware


class PyxleTelemetryMiddleware(BaseHTTPMiddleware):
		async def dispatch(self, request, call_next):
			request_id = uuid.uuid4().hex[:8]
			request.state.pyxle_demo = {
				"requestId": request_id,
				"issuedAt": datetime.now(tz=timezone.utc).isoformat(),
				"path": request.url.path,
			}
			started = time.perf_counter()
			response = await call_next(request)
			elapsed_ms = (time.perf_counter() - started) * 1000
			response.headers.setdefault("x-pyxle-demo", f"{elapsed_ms:.1f}ms")
			response.headers.setdefault("x-pyxle-request", request_id)
			return response
```

Restart `pyxle dev` after editing the config, then curl any route to confirm the header injection. Pyxle automatically prepends the project root to `sys.path` so these modules import correctly without extra packaging tricks.

### Route-aware policies

Phase 6 introduces dedicated hooks for page + API routes without forcing you to wrap the whole Starlette app. Add a `routeMiddleware` block to `pyxle.config.json` to register async policies that receive `(context, request, call_next)`:

```jsonc
{
	"routeMiddleware": {
		"pages": ["middlewares.policies:enforce_signed_in"],
		"apis": ["middlewares.policies:record_audit_trail"]
	}
}
```

Pyxle ships with default policies that keep `request.scope["pyxle"]["route"]` populated (path, loader info, hashed artifacts) and automatically returns `405` when an API request uses a verb outside the supported set. Custom hooks stack after the defaults, so you can inspect `context.target` (`"page"` or `"api"`) and attach additional state before calling `await call_next(request)`.

## Deployment

Use `pyxle build` to compile production artifacts and `pyxle serve` to run them with Uvicorn (no Vite required).

```bash
# Build to ./dist (override with --out-dir)
pyxle build --out-dir dist

# Serve the built app without Vite (runs pyxle build first unless --skip-build is set)
pyxle serve --dist-dir dist --host 0.0.0.0 --port 8080 --log-format json
# Skip static mounts when assets live behind a CDN or object store
pyxle serve --dist-dir dist --no-serve-static
```

Need faster subsequent builds? Append `--incremental` when re-running `pyxle build` to reuse the `.pyxle-build/` cache so only modified pages/APIs and assets are recompiled before the artifacts are copied into `dist/`.

`pyxle serve` automatically loads `dist/page-manifest.json`, mounts `dist/public` at `/`, exposes hashed bundles under `/client`, and starts the Starlette app with readiness probes enabled. Pass `--skip-build` when deploying prebuilt artifacts (for example, CI/CD pipelines that archive `dist/`).

See [`docs/deployment.md`](docs/deployment.md) for the full checklist covering prerequisites, readiness probes, and CI recommendations.

`pyxle build` prints the paths of every generated artifact upon completion:

- **Client manifest** — `dist/client/manifest.json` (emitted by Vite).
- **Page manifest** — `dist/page-manifest.json` (maps routes to server metadata + bundled assets).
- **Server modules** — `dist/server/`.
- **Metadata** — `dist/metadata/`.
- **Public assets** — `dist/public/` (skipped when the project lacks a `public/` directory).
- **Artifacts** — the root `dist/` directory (or your `--out-dir` value).

## Generated Project Structure

```text
my-awesome-app/
├── .gitignore
├── pyxle.config.json
├── package.json
├── pages/
│   ├── layout.pyx
│   ├── index.pyx
│   ├── projects/
│   │   ├── index.pyx
│   │   └── template.pyx
│   ├── diagnostics.pyx
│   ├── components/
│   │   ├── __init__.py
│   │   ├── head.py
│   │   ├── layout.jsx
│   │   └── site.py
│   └── api/
│       └── pulse.py
├── middlewares/
│   ├── __init__.py
│   └── telemetry.py
├── public/
│   ├── favicon.ico
│   ├── scripts/
│   │   └── pyxle-effects.js
│   └── styles/
│       └── pyxle.css
└── requirements.txt
```

## Shared layout primitives

Every scaffolded project now includes reusable helpers under
`pages/components/` so you can compose consistent pages immediately:

- `head.py` exports `build_head()` for safe `<head>` fragments.
- `layout.jsx` exports `RootLayout`, `Link`, and `SectionLabel`.
- `site.py` exports `build_page_head()`, `base_page_payload()`, and `site_metadata()` so every page can share navigation + head tags.
- `layout.pyx` wraps every page with the shared chrome and uses the new `Slot` helper from `pyxle/client` so routes can push hero/CTA content without importing `RootLayout` directly.
- `pages/projects/template.pyx` demonstrates a nested template that scopes styling for a specific route tree while still delegating data and slots to the leaf page.

Read more about how to customize these pieces in
[`docs/components.md`](docs/components.md).

## Tailwind CSS

Pyxle works with Tailwind the same way any Vite-powered React app does. Follow
the step-by-step integration guide in [`docs/tailwind.md`](docs/tailwind.md)
to add the dependencies, configure the `content` globs for `.pyx` files, and
import your generated stylesheet inside the JavaScript portion of a page.

## Development

Install the project with the optional development dependencies and run the tests:

```bash
pip install -e .[dev]
pytest
```

The test suite enforces 95% coverage for the CLI package.
