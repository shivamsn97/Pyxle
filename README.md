<p align="center">
  <br />
  <a href="https://pyxle.dev">
    <img src=".github/pyxle-logo.svg" alt="Pyxle" height="52" />
  </a>
  <br />
  <br />
  <strong>The Python full-stack framework.</strong>
  <br />
  Server logic in Python. UI in React. One file.
  <br />
  <br />
  <a href="https://pypi.org/project/pyxle-framework/"><img src="https://img.shields.io/pypi/v/pyxle-framework?color=22c55e&labelColor=0a0a0b&label=pypi" alt="PyPI" /></a>
  &nbsp;
  <a href="https://pyxle.dev"><img src="https://img.shields.io/badge/pyxle.dev-0a0a0b?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDE2IDE2Ij48Y2lyY2xlIGN4PSI4IiBjeT0iOCIgcj0iNiIgZmlsbD0iIzIyYzU1ZSIvPjwvc3ZnPg==&label=" alt="Website" /></a>
</p>

---

```python
# pages/index.pyx

@server
async def load(request):
    return {"message": "Hello from Python"}

# --- JSX ---
export default function Home({ data }) {
    return <h1>{data.message}</h1>;
}
```

Pyxle compiles `.pyx` files into Python server modules and React client components.
`@server` loaders run on the backend, SSR renders the HTML, React hydrates on the client.

## Get started

```bash
pip install pyxle-framework
pyxle init my-app && cd my-app
pyxle install
pyxle dev
```

Open **http://localhost:8000**.

## Features

**`.pyx` files** -- Python + React in a single file, split at compile time
**File-based routing** -- `pages/` maps to URLs, dynamic segments with `[param].pyx`
**SSR** -- Server-side rendering via esbuild + React 18
**`@server` / `@action`** -- Typed data loading and form mutations
**Layouts** -- Nested layouts and templates with slot composition
**Vite HMR** -- Fast refresh in development
**Tailwind** -- Pre-configured out of the box
**Production build** -- `pyxle build` + `pyxle serve` for deployment

## Documentation

Full docs are in the [`docs/`](docs/README.md) directory:

- [Quick Start](docs/getting-started/quick-start.md)
- [`.pyx` Files](docs/core-concepts/pyx-files.md)
- [Routing](docs/core-concepts/routing.md)
- [Data Loading](docs/core-concepts/data-loading.md)
- [Server Actions](docs/core-concepts/server-actions.md)
- [Layouts](docs/core-concepts/layouts.md)
- [Deployment](docs/guides/deployment.md)
- [CLI Reference](docs/reference/cli.md)
- [Configuration](docs/reference/configuration.md)

## CLI

```
pyxle init <name>     Scaffold a new project
pyxle install         Install Python + Node dependencies
pyxle dev             Development server with HMR
pyxle build           Production build
pyxle serve           Serve the production build
```

## Requirements

Python 3.10+ and Node.js 18+.

## Contributing

```bash
git clone https://github.com/pyxle-framework/pyxle.git
cd pyxle
pip install -e ".[dev]"
pytest
```

## Links

- [pyxle.dev](https://pyxle.dev)
- [PyPI](https://pypi.org/project/pyxle-framework/)
- [Issues](https://github.com/pyxle-framework/pyxle/issues)
