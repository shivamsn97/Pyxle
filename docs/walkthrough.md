# Pyxle MVP Walkthrough

This guide covers the happy path from scaffolding a new project to viewing the
SSR output in your browser. Follow the steps below whenever you want to verify
that the CLI, compiler, dev server, and overlay tooling are working together.

## 1. Scaffold a project

```bash
pyxle init pyxle-demo
cd pyxle-demo
```

The generated structure includes the showcase homepage, an API route, and shared
layout helpers inside `pages/components/`.

## 2. Install dependencies

```bash
pyxle install
```

The installer runs both `python -m pip install -r requirements.txt` and `npm install`
inside your project (pass `--no-python` or `--no-node` to skip either step). Prefer a
single command? Start with `pyxle init pyxle-demo --install` to scaffold and install in
one go. `requirements.txt` contains the Python runtime dependencies while
`package.json` installs React, Vite, and the dev server tooling.

## 3. Run the development server

```bash
pyxle dev
```

The CLI compiles `.pyx` files, launches Vite, and starts Starlette on
`http://127.0.0.1:8000`. The terminal output lists both URLs alongside the
watcher status.

## 4. Explore the scaffolded UI

Open the homepage and the supporting demo routes:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/projects`
- `http://127.0.0.1:8000/diagnostics`

Need to confirm your routing is wired correctly? Visit any missing path—for example,
`http://127.0.0.1:8000/does-not-exist`—to see the scaffolded catch-all page rendered from
`pages/[...slug].pyx`. It responds with a 404 status and a button that immediately brings you
back to the homepage, so you have a ready-made 404 experience from day one.

The overview page stays intentionally minimal so you can see how navigation and
shared metadata work, while `/projects` and `/diagnostics` exercise async
loaders, shared layout primitives, and React interactivity. The diagnostics page
also pings `/api/pulse` on an interval so you can watch middleware and API data
update live.

## 5. Experience client-side navigation

Pyxle now mirrors Next.js-style routing on the client. After the first SSR
response hydrates, the browser intercepts same-origin `<a>` clicks, requests the
target path with an `x-pyxle-navigation: 1` header, diff-applies the `<head>`
markup between the sentinel `<meta data-pyxle-head-start>`/`-end` markers, and
re-renders the React tree without a full page reload (no more white flash while
CSS links reload). Back/forward history entries use the same data channel, so
navigating across `/`, `/projects`, and `/diagnostics` feels instant while
keeping loader data fresh.

Projects can opt into these SPA semantics explicitly by importing the runtime
Link helper:

```jsx
import { Link } from 'pyxle/client';

export function Nav() {
  return (
    <nav>
      <Link href="/projects" prefetch>
        Projects
      </Link>
    </nav>
  );
}
```

The helper automatically prefetches the JSON payload + component module as soon
as the link scrolls into view (mirroring Next.js’ `IntersectionObserver`
behavior) and on hover; pass `prefetch={false}` to opt out for specific links.
It also falls back to a full reload for external URLs. Need a traditional
navigation for an anchor or button? Add `data-pyxle-router="off"` to the
element and it will bypass the SPA router and perform a normal page load.

Behind the scenes Pyxle keeps the previous route's stylesheets mounted until the
next page's CSS finishes loading, matching Next.js' "no flash" experience even
when each page ships bespoke styles. You can watch this by throttling the
network in dev tools—the content stays styled throughout the transition.

### 6. Advanced routing semantics

The file system router now understands the same shorthand you may have used in
Next.js:

- Directories wrapped in parentheses (for example `(dashboard)/projects`) act as
  route groups for organization only; they never appear in the public URL.
- Files named `[...slug].pyx` (or `.py` under `pages/api/`) become Starlette
  catch-alls using `{slug:path}` so `/posts/a/b/c` resolves to a single
  handler.
- `[[...slug]].pyx` registers both the base route and the catch-all variant, so
  `/docs` and `/docs/anything` reach the same code without an extra redirect.

The compiler persists these aliases in page metadata, letting the dev server,
SSR pipeline, manifest builder, and SPA router keep every variant perfectly in
sync.

## 6. Trigger the developer overlay (optional)

Introduced in Phase 5 and expanded here, the overlay now includes
loader/renderer/hydration breadcrumbs. You can trigger it by throwing an error
in a loader or component:

```python
@server
async def load_showcase(request):
    raise RuntimeError("demo failure")
```

Refresh the browser to see the overlay show the failing stage, the stack trace,
and actionable breadcrumbs.

## 7. Add Tailwind, layouts, or templates when ready

The scaffold now ships with `pages/layout.pyx` plus a route-scoped
`pages/projects/template.pyx`. Both files use the new `Slot` helper from
`pyxle/client`, so leaf pages only export `slots = { hero: (...) }` instead of
manually importing `RootLayout`. You can:

- Define global chrome in `layout.pyx` using `<Slot name="hero" props={{ data }} />`.
- Add directory-specific `template.pyx` files (they reset slot defaults when
  encountered, so you can theme subsections like `/projects`).
- Keep shared helpers under `pages/components/` for head/meta utilities.

When you're ready for utility-first styling, follow
[`docs/tailwind.md`](tailwind.md) to install Tailwind, create a stylesheet, and
import it from your `.pyx` modules.

## 8. Next steps

- Update `pages/index.pyx`, `pages/projects/index.pyx`, or `pages/diagnostics.pyx` with your own content (and tweak `pages/layout.pyx` / `pages/projects/template.pyx` as needed).
- Add additional routes under `pages/` (file-based routing mirrors Next.js).
- Run `pyxle build --no-debug` once you're ready to verify production manifests
  before deployment (see [`docs/deployment.md`](deployment.md)).
