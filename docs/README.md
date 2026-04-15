# Pyxle Documentation

Pyxle is a Python-first full-stack web framework that brings the Next.js developer experience to the Python ecosystem. Write server logic in Python, UI in React, and ship them together in `.pyxl` files.

**Current version:** 0.2.3 (beta)

---

## Getting Started

New to Pyxle? Start here.

- [Installation](getting-started/installation.md) -- Prerequisites and install steps
- [Quick Start](getting-started/quick-start.md) -- Create your first Pyxle app in 5 minutes
- [Project Structure](getting-started/project-structure.md) -- What each file and folder does

## Core Concepts

The fundamentals of how Pyxle works.

- [`.pyxl` Files](core-concepts/pyxl-files.md) -- How Python and React coexist in one file
- [Routing](core-concepts/routing.md) -- File-based routing, dynamic segments, catch-all routes
- [Data Loading](core-concepts/data-loading.md) -- `@server` loaders and passing props to components
- [Server Actions](core-concepts/server-actions.md) -- `@action` mutations, `<Form>`, and `useAction`
- [Layouts](core-concepts/layouts.md) -- Shared layouts, templates, and page composition

## Guides

Practical guides for common tasks.

- [Styling](guides/styling.md) -- Tailwind CSS, global stylesheets, and inline styles
- [Head Management](guides/head-management.md) -- `<Head>` component, the `HEAD` variable, and dynamic meta tags
- [API Routes](guides/api-routes.md) -- Building JSON APIs under `pages/api/`
- [Middleware](guides/middleware.md) -- Application-level and route-level middleware
- [Environment Variables](guides/environment-variables.md) -- `.env` files, `PYXLE_PUBLIC_` prefix, and config overrides
- [Error Handling](guides/error-handling.md) -- `LoaderError`, `ActionError`, `error.pyxl`, and `not-found.pyxl`
- [Client Components](guides/client-components.md) -- `<Script>`, `<Image>`, `<ClientOnly>`, and `<Link>`
- [Security](guides/security.md) -- CSRF protection, CORS, and HEAD sanitisation
- [Deployment](guides/deployment.md) -- `pyxle build`, `pyxle serve`, and hosting in production
- [Pyxle for AI coding agents](guides/for-ai-agents.md) -- Why Pyxle is the framework most optimised for pairing with Claude, Cursor, Copilot, and other AI coding agents

## Reference

Complete API and configuration reference.

- [CLI Commands](reference/cli.md) -- Every command, flag, and option
- [Configuration](reference/configuration.md) -- Full `pyxle.config.json` schema
- [Runtime API](reference/runtime-api.md) -- `@server`, `@action`, `LoaderError`, `ActionError`
- [Client API](reference/client-api.md) -- All client-side components and hooks

## Architecture

The complete architecture handbook -- a guided tour of how Pyxle is built on the inside, written for everyone from "I just installed Pyxle yesterday" to "I want to send a PR that touches the SSR worker pool."

- [Architecture overview](architecture/README.md) -- Start here. Index of every architecture doc.
- [Request lifecycle](architecture/overview.md) -- One HTTP request, end to end, in one read.
- [The .pyxl file format](architecture/pyxl-files.md) -- Why Pyxle invented a new file extension.
- [The parser](architecture/parser.md) -- How `.pyxl` files get split into Python and JSX using only `ast.parse`. The most sensitive code in the framework.
- [The compiler](architecture/compiler.md) -- How parsed pages become `.py` + `.jsx` + `.json` artifacts.
- [Routing](architecture/routing.md) -- File-based routing, dynamic segments, catch-all routes, layouts, error boundaries.
- [The dev server](architecture/dev-server.md) -- Starlette + Vite + the file watcher + the incremental builder + the WebSocket overlay.
- [Server-side rendering](architecture/ssr.md) -- Loader execution, the Node.js worker pool, head merging, document assembly, streaming.
- [Build and serve](architecture/build-and-serve.md) -- What `pyxle build` and `pyxle serve` do for production.
- [The runtime](architecture/runtime.md) -- The `@server` and `@action` decorators and the *zero-magic* contract.
- [The CLI](architecture/cli.md) -- `pyxle init`, `dev`, `build`, `serve`, `check`. Config precedence and tolerant-mode validation.

## Advanced

For framework contributors and power users.

- [SSR Pipeline](advanced/ssr-pipeline.md) -- High-level SSR overview (see [architecture/ssr.md](architecture/ssr.md) for the full deep-dive)
- [Compiler Internals](advanced/compiler-internals.md) -- High-level compiler overview (see [architecture/compiler.md](architecture/compiler.md) and [architecture/parser.md](architecture/parser.md) for the full deep-dive)

## FAQ

- [Frequently Asked Questions](faq.md)

---

## Links

- GitHub: [github.com/pyxle-framework/pyxle](https://github.com/pyxle-framework/pyxle)
- Issues: [github.com/pyxle-framework/pyxle/issues](https://github.com/pyxle-framework/pyxle/issues)
- Install: `pip install pyxle-framework`
- PyPI: [pypi.org/project/pyxle-framework](https://pypi.org/project/pyxle-framework/)
