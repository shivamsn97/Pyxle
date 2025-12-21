# Project Structure

Pyxle projects mirror the layout of the default scaffold produced by `pyxle init`. Every folder has a matching runtime component so you always know where app behaviour lives, and nothing is framework-only boilerplate.

```
my-app/
├── pages/                 # Source of truth for routes, layouts, and client assets
│   ├── layout.pyx         # App-wide layout (similar to Next.js layout)
│   ├── index.pyx          # Home route; loader + component live together
│   ├── api/               # Starlette-compatible API modules
│   └── styles/            # Tailwind entrypoints; compiled CSS copied to public/
├── public/                # Static assets served verbatim
│   └── styles/tailwind.css
├── pyxle.config.json      # Project-specific dev server + middleware config
├── requirements.txt       # Python dependencies (Starlette, httpx, uvicorn)
├── package.json           # React, Vite, Tailwind toolchain
└── .pyxle-build/          # Generated server/client/metadata artifacts (gitignored)
```

## Runtime directories

| Directory | Owned by | Purpose |
| --- | --- | --- |
| `.pyxle-build/client` | Compiler + devserver | Browser-ready JSX outputs and bootstrap files fed to Vite. |
| `.pyxle-build/server` | Compiler | Python modules that Starlette imports for page loaders and API routes. |
| `.pyxle-build/metadata` | Compiler | JSON descriptors (head tags, route info) consumed by the SSR renderer. |
| `public/` | You | Assets copied as-is in dev and production. Vite proxy serves `/branding/*`, `/styles/*`, etc. |

## Generated helpers

`pyxle dev` writes a handful of helper files so the runtime can work:

- `client-entry.js` + `routes-manifest.json` inside `.pyxle-build/client/` describe every page for client navigation.
- `metadata/pages/**/*.json` capture loader/head metadata for SSR.
- `server/pages/**/*.py` wrap loader results so Starlette can stream HTML via `pyxle.ssr.build_page_response`.

## Developer workflow tips

```sh
# Fast feedback loop
pyxle dev                   # Starts Starlette + Vite with React Fast Refresh
pyxle build --incremental   # Recompile only the files that changed
pyxle serve --skip-build    # Preview the production bundle without Vite
```

- Keep `.pyxle-build/` gitignored; delete it when switching branches to force a clean rebuild.
- Edit `pyxle.config.json` to register custom middleware or change the default dev server ports without touching CLI flags.
- Use your preferred browser automation or manual cURL checks against `pyxle dev --host 0.0.0.0` to verify routes end-to-end; the Starlette proxy mirrors responses exactly.

## Compare with Next.js

- `pages/` resembles the legacy Next.js `pages/` directory, but each file is dual (Python + JSX) instead of JavaScript-only.
- `.pyxle-build/` is similar to Next.js `.next/`; it should stay out of version control.
- API routes live under `pages/api/` just like Next.js, but they are pure Starlette modules.

Continue with [Authoring `.pyx` files](../fundamentals/pyx-files.md) for the file format or [File-based routing](../routing/file-based-routing.md) to see how filenames become routes.

---
**Navigation:** [← Previous](what-is-pyxle.md) | [Next →](../fundamentals/index.md)
