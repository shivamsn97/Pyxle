# What is Pyxle?

Pyxle is a Python-first take on the Next.js mental model. Pages live in `pages/`, each `.pyx` file bundles its server loader and React component, and the dev server glues Starlette, Vite, and a Node-based SSR runtime into a single workflow. If you already know `app/` routes, file-based layouts, or data loaders from Next.js, Pyxle gives you the same ergonomics without leaving Python.

## Guiding ideas

1. **One file per feature** – Python loader + JSX live side-by-side so business logic stays near the UI.
2. **Instant routes** – The compiler turns filenames into Starlette routes (`pages/posts/[id].pyx` → `/posts/{id}`).
3. **Batteries-included tooling** – `pyxle dev` boots Starlette, proxies to Vite, watches Tailwind, and surfaces overlay errors.
4. **Predictable SSR** – A thin Node shim (`pyxle/ssr/render_component.mjs`) renders React components and streams the result back to Starlette.
5. **No custom runtime contracts** – You are writing pure async Python (loaders) and React 18 function components (client).

## Architecture at a glance

```
pages/*.pyx ──┐  compile_file()              ComponentRenderer      Browser
			  ├─> server artifacts (.py) ──> Starlette routes ──┐   ▲
			  └─> client artifacts (.jsx) ─► Vite dev server ──┼───┘
													   ▲      │
									 overlay + watcher└───────┘
```

- **Compiler** emits three artifacts per route (server module, client bundle stub, metadata).
- **Dev server** mounts Starlette for loaders + APIs and proxies `/client/*` to Vite so React refresh stays instant.
- **SSR runtime** shells out to Node to render components, injects head tags + global assets, and streams HTML back.
- **Client runtime** hydrates the response, powers `<Link>`, and keeps the overlay connected for debug hints.

## Compare with Next.js

| Concept | Next.js | Pyxle |
| --- | --- | --- |
| File-based routing | `app/blog/[slug]/page.tsx` | `pages/blog/[slug].pyx` |
| Data loaders | `export async function generateMetadata()` + `fetch()` | `@server async def load_post(request)` returning dict or `(dict, status)` |
| Styling | Tailwind via PostCSS | Tailwind CLI via `npm run dev:css`, assets copied to `public/` |
| Dev server | `next dev` (Node) | `pyxle dev` (Starlette + Vite proxy) |
| SSR runtime | React Server Components | React 18 SSR via Node subprocess |

## When to reach for Pyxle

- You prefer Python for data access, validation, and infra glue, but still want React on the client.
- You need server routes, API routes, and static assets to share helpers without an HTTP boundary.
- You want a thin abstraction: Starlette middleware, httpx clients, or `uvicorn` knobs are not hidden.

## Quick start

```bash
pyxle init my-app --install
cd my-app
npm run dev:css    # watches Tailwind into public/styles/tailwind.css
pyxle dev
```

Open `pages/index.pyx`, edit the loader or JSX, and the dev server will rebuild, invalidate import caches, and trigger the Vite overlay automatically.

## Where features live

- CLI commands: `pyxle/cli/__init__.py`
- Compiler & parser: `pyxle/compiler/`
- Dev server + watcher: `pyxle/devserver/`
- SSR runtime: `pyxle/ssr/`
- Templates: `pyxle/templates/scaffold/`

Use the [project structure guide](project-structure.md) to understand how these folders map to runtime behaviours.

## Loader round-trip (request/response trace)

```
GET /projects HTTP/1.1
Host: 127.0.0.1:8000
Accept: text/html

Starlette route ➜ import compiled server module ➜ call @server loader
Loader returns {'projects': [...], 'timestamp': '...'}
SSR renderer ➜ Node renders React component ➜ HTML streamed back

HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Set-Cookie: pyxle-dev=1; SameSite=Lax

<!doctype html>
<html data-theme="dark">...
```

This is the same flow `pyxle serve` uses in production—the only difference is that `pyxle dev` also keeps Vite and the overlay websocket alive for instant feedback.
