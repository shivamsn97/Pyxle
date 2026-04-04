# Pyxle Documentation

Pyxle is a Python-first full-stack web framework that brings the Next.js developer experience to the Python ecosystem. Write server logic in Python, UI in React, and ship them together in `.pyx` files.

**Current version:** 0.1.0 (beta)

---

## Getting Started

New to Pyxle? Start here.

- [Installation](getting-started/installation.md) -- Prerequisites and install steps
- [Quick Start](getting-started/quick-start.md) -- Create your first Pyxle app in 5 minutes
- [Project Structure](getting-started/project-structure.md) -- What each file and folder does

## Core Concepts

The fundamentals of how Pyxle works.

- [`.pyx` Files](core-concepts/pyx-files.md) -- How Python and React coexist in one file
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
- [Error Handling](guides/error-handling.md) -- `LoaderError`, `ActionError`, `error.pyx`, and `not-found.pyx`
- [Client Components](guides/client-components.md) -- `<Script>`, `<Image>`, `<ClientOnly>`, and `<Link>`
- [Security](guides/security.md) -- CSRF protection, CORS, and HEAD sanitisation
- [Deployment](guides/deployment.md) -- `pyxle build`, `pyxle serve`, and hosting in production

## Reference

Complete API and configuration reference.

- [CLI Commands](reference/cli.md) -- Every command, flag, and option
- [Configuration](reference/configuration.md) -- Full `pyxle.config.json` schema
- [Runtime API](reference/runtime-api.md) -- `@server`, `@action`, `LoaderError`, `ActionError`
- [Client API](reference/client-api.md) -- All client-side components and hooks

## Advanced

For framework contributors and power users.

- [SSR Pipeline](advanced/ssr-pipeline.md) -- How server-side rendering works under the hood
- [Compiler Internals](advanced/compiler-internals.md) -- How `.pyx` files are parsed and compiled

## FAQ

- [Frequently Asked Questions](faq.md)

---

## Links

- GitHub: [github.com/pyxle-framework/pyxle](https://github.com/pyxle-framework/pyxle)
- Issues: [github.com/pyxle-framework/pyxle/issues](https://github.com/pyxle-framework/pyxle/issues)
- Install: `pip install pyxle-framework`
- PyPI: [pypi.org/project/pyxle-framework](https://pypi.org/project/pyxle-framework/)
