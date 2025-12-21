# Pyxle

Pyxle is a Python-first full-stack framework that pairs a Typer-powered CLI with Starlette, Vite, and React to deliver a Next.js-style developer experience. The MVP currently focuses on the project scaffolding workflow.

## Project Links

- Homepage — [pyxle.dev](https://pyxle.dev)
- Docs — [pyxle.dev/docs](https://pyxle.dev/docs)
- GitHub — [github.com/shivamsn97/pyxle](https://github.com/shivamsn97/pyxle)
- PyPI — [pypi.org/project/pyxle](https://pypi.org/project/pyxle/)
- Issues — [github.com/shivamsn97/pyxle/issues](https://github.com/shivamsn97/pyxle/issues)
- Maintainer — Shivam Saini (<hello@pyxle.dev>)

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

Run `npm run dev:css` in a second terminal to keep `/public/styles/tailwind.css`
in sync; the scaffold links this file directly from the shared head so SSR stays
fully styled even when JavaScript is disabled.
`pyxle build` automatically invokes `npm run build`, which runs the Tailwind
`build:css` script before delegating to Vite, so production bundles always pick
up your latest stylesheet without extra commands.

The scaffold now mirrors a Next.js landing page: a single `.pyx` route renders a Tailwind-powered hero, feature cards, and quick-start commands with a built-in light/dark toggle. Branding assets (mark, wordmark, and grid pattern) live in `public/branding/`, Tailwind ships via `tailwind.config.cjs` + `postcss.config.cjs`, and the compiled stylesheet (`public/styles/tailwind.css`) is linked directly from the shared head so SSR answers are fully styled even when JavaScript is disabled. Run `npm run dev:css` alongside `pyxle dev` to keep the stylesheet fresh while editing.

Prefer a narrative version? Follow the step-by-step guide that starts in
[`docs/README.md`](docs/README.md) to see the CLI, compiler, and dev server
working together with screenshots and overlay tips.

## Available Commands

- `pyxle init <name>` — Scaffold a new project with starter pages, API route, and configuration files.
- `pyxle init <name> --force` — Overwrite an existing directory.
- `pyxle init <name> --install` — Scaffold and immediately install Python + Node dependencies.
- `pyxle init <name> --template <template>` — Placeholder for future template variants (only `default` is currently accepted).
- `pyxle install [path]` — Runs `python -m pip install -r requirements.txt` and `npm install` (use `--no-python` / `--no-node` to skip either step).
- `pyxle serve [path] --dist-dir <dir>` — Boot the production Starlette app without Vite. Runs `pyxle build` by default, then serves the contents of `dist/` via Uvicorn (add `--skip-build` when you only want to reuse existing artifacts). Disable the built-in static mounts with `--no-serve-static` if a CDN or edge proxy owns your asset hosting.

## Custom middleware hooks

Projects can inject Starlette-compatible middleware globally via `pyxle.config.json`. The scaffold leaves the list empty so you opt-in only when needed:

```jsonc
{
	"middleware": []
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

See [`docs/deployment/deployment.md`](docs/deployment/deployment.md) for the full checklist covering prerequisites, readiness probes, and CI recommendations.

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
├── postcss.config.cjs
├── package.json
├── tailwind.config.cjs
├── pages/
│   ├── layout.pyx
│   ├── index.pyx
│   ├── styles/
│   │   └── tailwind.css
│   └── api/
│       └── pulse.py
├── public/
│   ├── favicon.ico
│   ├── branding/
│   │   ├── pyxle-mark.svg
│   │   ├── pyxle-wordmark-dark.svg
│   │   ├── pyxle-wordmark-light.svg
│   │   └── pyxle-grid.svg
│   └── styles/
│       └── tailwind.css
└── requirements.txt
```

## Starter experience

`pages/index.pyx` now mirrors a modern Next.js marketing page:

- **Single loader:** The Python section seeds hero copy, feature cards, and command examples—edit the dicts to brand your project.
- **Tailwind everywhere:** `pages/index.pyx` links `/styles/tailwind.css` directly in `HEAD`. Run `npm run dev:css` while developing, and let `pyxle build` trigger `npm run build` (which runs `build:css` first) so production SSR stays styled without relying on JavaScript.
- **Theme toggle:** A tiny hook stores the preferred mode in `localStorage` and toggles the `dark` class on `<html>`.
- **Brand kit:** `/public/branding/` contains the Pyxle mark, wordmark, and background grid so the UI feels intentional out of the box.

Use this page as a launchpad: duplicate it for additional routes, or strip it down to a blank slate once you understand the loader/component flow.

## Tailwind CSS

New projects already ship with Tailwind, PostCSS, and the official forms & typography plugins wired up:

- `tailwind.config.cjs` watches both `.pyx` sources and the generated `.pyxle-build/client/pages/**/*.jsx` files.
- `postcss.config.cjs` keeps Vite aware of the Tailwind + Autoprefixer plugins.
- `pages/styles/tailwind.css` contains the `@tailwind` directives. Run `npm run dev:css` during development, and rely on `pyxle build` (or a manual `npm run build`) to execute the `build:css` script before Vite so every SSR response is fully styled.

Need to extend the theme, add custom layers, or change the content globs? Follow the playbook in [`docs/styling/tailwind.md`](docs/styling/tailwind.md) for tips on overriding the defaults.

## Development

Install the project with the optional development dependencies, then exercise the supported CLI commands before contributing changes:

```bash
pip install -e .[dev]
pyxle dev --help
pyxle build --help
```

Run `pyxle dev` or `pyxle build` locally to validate your changes; there is no officially supported automated test harness yet.
