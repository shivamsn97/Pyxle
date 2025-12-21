# CLI Reference

Pyxle's CLI is implemented with Typer in `pyxle/cli/__init__.py`. Every command shares the same logger (`ConsoleLogger`) so output stays consistent.

## Commands

### `pyxle init <name>`

- Creates a new scaffold using templates from `pyxle/cli/templates.py`.
- Flags:
  - `--force` overwrite existing directories.
  - `--install/--no-install` run pip/npm installers automatically.
  - `--template` (placeholder for future templates).
- Outputs next steps: install deps, run Tailwind watcher, start dev server.

### `pyxle install [directory]`

- Installs Python deps via `pip install -r requirements.txt` and Node deps via `npm install`.
- Toggle each side with `--python/--no-python` and `--node/--no-node`.

### `pyxle dev`

- Starts the dev server.
- Options mirror `pyxle.config.json`: `--host`, `--port`, `--vite-host`, `--vite-port`, `--debug`, `--config`, `--print-config`.
- Uses Watchdog for rebuilds, Vite proxy for assets, overlay for errors.

### `pyxle build`

- Runs the production build pipeline.
- Common flags: `--config`, `--out-dir`, `--incremental`.
- Emits paths to the client manifest, page manifest, server artifacts, metadata, and public assets.

### `pyxle serve`

- Serves a production build via Uvicorn.
- Flags: `--dist-dir`, `--skip-build`, `--serve-static/--no-serve-static`, plus host/port and config overrides.

### `pyxle compile` *(hidden)*

- Utility for compiling a single `.pyx` file into `.pyxle-build` to debug parser/renderer issues.

## Logging formats

Use `--log-format json` to emit machine-readable logs (handy for CI). The default `console` style prints steps, warnings, and errors with emojis for readability.

## Compare with Next.js

| Task | Next.js CLI | Pyxle CLI |
| --- | --- | --- |
| Scaffold | `npx create-next-app` | `pyxle init` |
| Dev server | `next dev` | `pyxle dev` |
| Build | `next build` | `pyxle build` |
| Serve | `next start` | `pyxle serve` |

Use [`pyxle.config.json`](config.md) to control defaults so you rarely need to pass CLI flags.
