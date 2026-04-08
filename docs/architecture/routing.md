# Routing

Pyxle uses **file-based routing**: the path of a `.pyx` file inside
your `pages/` directory *is* its URL. There is no `@app.route("/")`
decorator. There is no router config file. There is no list of routes
maintained by hand. The directory structure is the routing table.

This doc explains how that works, exhaustively. By the end you'll know
exactly which URL each file maps to, what the dynamic segment syntax
means, how layouts compose, and how a request gets dispatched to the
right handler.

**Files:**
- `routing/paths.py` (~135 lines) — file path → URL conversion
  (zero dependencies, importable from anywhere)
- `devserver/routes.py` (~280 lines) — `PageRoute`, `ApiRoute`,
  `ActionRoute`, `RouteTable` dataclasses
- `devserver/registry.py` (~380 lines) — loads metadata, builds
  the route table at startup

---

## The basic mapping

The simplest case is one file per URL:

```
pages/
├── index.pyx                    →  /
├── about.pyx                    →  /about
└── contact.pyx                  →  /contact
```

Three rules turn the file path into the URL:

1. **Strip the `.pyx` extension.**
2. **Drop `index` segments** — `index.pyx` collapses to its parent.
3. **Prefix with `/`** — every route starts at the root.

A nested directory becomes a path segment:

```
pages/
├── posts/
│   ├── index.pyx                →  /posts
│   ├── popular.pyx              →  /posts/popular
│   └── archive/
│       └── 2025.pyx             →  /posts/archive/2025
└── settings/
    └── index.pyx                →  /settings
```

That's the entire convention for static routes. There's nothing
clever happening — `routing/paths.py:24-65` is the function that
does it, and it's about 40 lines of straightforward string handling.

> **Pyxle in Next.js terms:** This is exactly how Next.js's `pages/`
> directory works. The conventions are deliberately compatible because
> file-based routing is one of those design choices that's hard to
> improve on.

---

## Dynamic segments — `[id]`

Real apps need URLs that contain parameters. Pyxle uses **square
bracket** syntax in filenames to declare them:

```
pages/
└── posts/
    └── [id].pyx                 →  /posts/{id}
```

The brackets become a Starlette path parameter. Inside the loader,
you read it from `request.path_params`:

```python
@server
async def load_post(request):
    post_id = request.path_params["id"]
    post = await db.fetch_post(post_id)
    return {"post": post}
```

The parameter name is whatever you put inside the brackets:

```
pages/
├── users/[username].pyx         →  /users/{username}
├── docs/[section].pyx           →  /docs/{section}
└── shop/[productSlug].pyx       →  /shop/{productSlug}
```

You can have multiple dynamic segments at different levels:

```
pages/
└── orgs/
    └── [org]/
        └── repos/
            └── [repo]/
                └── settings.pyx →  /orgs/{org}/repos/{repo}/settings
```

Dynamic segments can sit alongside static ones:

```
pages/
└── blog/
    ├── [year]/
    │   ├── index.pyx            →  /blog/{year}
    │   └── [slug].pyx           →  /blog/{year}/{slug}
    └── archive.pyx              →  /blog/archive
```

Routing is **most-specific-first**, so `/blog/archive` will match
`archive.pyx` rather than the dynamic `[year]/index.pyx`. (This is
Starlette's standard behaviour — Pyxle doesn't override it.)

### Parameter name sanitization

The parameter name inside brackets is sanitized for Starlette:
hyphens, dots, and special characters get replaced with underscores.
A name starting with a digit is prefixed with `_`. Empty brackets fall
back to `param` (or `slug` for catch-alls).

```python
def _sanitize_param_name(name):
    cleaned = name.replace("-", "_").replace(".", "_")...
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    if not cleaned:
        cleaned = "param"
    return cleaned
```

Source: `routing/paths.py:107`.

In practice this is invisible — name your parameters with regular
identifiers and you'll never notice. The sanitizer exists to make
sure that even unusual filenames don't break route registration.

---

## Catch-all segments — `[...slug]`

Sometimes a single route should match an arbitrary number of path
segments. For example, a docs site where the URL `/docs/getting-
started/installation` should be served by one component that reads
the path as a list.

Pyxle uses `[...name]` for this:

```
pages/
└── docs/
    └── [...slug].pyx            →  /docs/{slug:path}
```

The `path` converter tells Starlette to match everything (including
slashes). Inside the loader, `request.path_params["slug"]` is a
single string like `"getting-started/installation"`. You can split it
on `/` to get the segments.

Catch-all routes only match URLs with **at least one** segment after
the prefix. So `[...slug].pyx` matches `/docs/foo` and
`/docs/foo/bar` but **not** `/docs` itself.

If you want to match `/docs` *as well as* `/docs/foo`, you need the
optional catch-all (next section), or you can add an `index.pyx`
sibling:

```
pages/
└── docs/
    ├── index.pyx                →  /docs            (matches "/docs")
    └── [...slug].pyx            →  /docs/{slug:path}  (matches "/docs/anything/else")
```

---

## Optional catch-all — `[[...slug]]`

The double-bracket form matches everything **including** the empty
case:

```
pages/
└── shop/
    └── [[...path]].pyx          →  /shop/{path:path}  (primary)
                                     /shop              (alias)
```

This is the same as a catch-all plus an `index.pyx` sibling, but in
one file. It's useful when you have a single component that should
render for the entire URL space under a prefix — for example a
storefront that handles `/shop`, `/shop/electronics`, and
`/shop/electronics/laptops/macbook-pro` all with the same loader and
component.

Under the hood, Pyxle creates **two** Starlette routes for an
optional catch-all: a primary route and an alias. They're both
served by the same handler. The `RoutePathSpec` returned by
`route_path_variants_from_relative()` has both:

```python
RoutePathSpec(
    primary="/shop/{path:path}",
    aliases=("/shop",),
)
```

Source: `routing/paths.py:24-65`.

---

## Route groups — `(name)`

Sometimes you want to organize files in a folder *without* the folder
becoming part of the URL. Pyxle uses **parentheses** for this:

```
pages/
├── (marketing)/
│   ├── index.pyx                →  /
│   ├── about.pyx                →  /about
│   └── pricing.pyx              →  /pricing
└── (app)/
    ├── dashboard.pyx            →  /dashboard
    └── settings.pyx             →  /settings
```

The `(marketing)` and `(app)` segments are **invisible to routing**
but visible to layouts. This lets you apply different layouts to
different parts of the app — say, a marketing layout for the public
pages and an app shell for the authenticated section — without
forcing the routes themselves to be prefixed with `/marketing/` or
`/app/`.

You can nest route groups inside dynamic segments and vice versa:

```
pages/
├── (auth)/
│   ├── login.pyx                →  /login
│   └── signup.pyx               →  /signup
└── (dashboard)/
    └── orgs/
        └── [org]/
            └── settings.pyx     →  /orgs/{org}/settings
```

Source: `routing/paths.py:75` (just `_is_route_group` — six lines).

---

## A complete reference table

Here's every routing feature in one table:

| Source filename                              | Route                            | Notes |
|---|---|---|
| `pages/index.pyx`                            | `/`                              | Index of root |
| `pages/about.pyx`                            | `/about`                         | Static route |
| `pages/posts/index.pyx`                      | `/posts`                         | Index collapses |
| `pages/posts/[id].pyx`                       | `/posts/{id}`                    | Dynamic segment |
| `pages/posts/[id]/comments.pyx`              | `/posts/{id}/comments`           | Nested under dynamic |
| `pages/docs/[...slug].pyx`                   | `/docs/{slug:path}`              | Catch-all (>=1 segment) |
| `pages/shop/[[...path]].pyx`                 | `/shop/{path:path}`<br>`/shop`   | Optional catch-all (primary + alias) |
| `pages/(marketing)/about.pyx`                | `/about`                         | Group is invisible |
| `pages/(auth)/login.pyx`                     | `/login`                         | Group is invisible |
| `pages/api/health.py`                        | `/api/health`                    | API route (Python only) |
| `pages/layout.pyx`                           | *(not a route)*                  | Layout — wraps siblings |
| `pages/error.pyx`                            | *(not a route)*                  | Error boundary |
| `pages/not-found.pyx`                        | *(not a route)*                  | 404 boundary |

The last three are **special filenames** — they're not routes
themselves; they affect how other routes render. We'll cover them
in the next sections.

---

## Layouts

A `layout.pyx` file at any level of the tree wraps every route below
it. For example:

```
pages/
├── layout.pyx                   ← root layout, wraps everything
├── index.pyx                    →  /            (wrapped by root)
├── about.pyx                    →  /about       (wrapped by root)
└── dashboard/
    ├── layout.pyx               ← dashboard layout
    ├── index.pyx                →  /dashboard   (root → dashboard → page)
    └── settings.pyx             →  /dashboard/settings
```

The dashboard's `/dashboard/settings` route is rendered as:

```
RootLayout(
    DashboardLayout(
        SettingsPage({data})
    )
)
```

Layouts compose from outermost to innermost. The compiler generates a
**route module** in `.pyxle-build/client/routes/` that does the
nesting:

```jsx
// .pyxle-build/client/routes/dashboard/settings.jsx
import Page from '../../pages/dashboard/settings.jsx';
import DashboardLayout from '../../pages/dashboard/layout.jsx';
import RootLayout from '../../pages/layout.jsx';

export default function PyxleWrappedPage(props) {
    return (
        <RootLayout>
            <DashboardLayout>
                <Page {...props} />
            </DashboardLayout>
        </RootLayout>
    );
}
```

The page metadata's `client_path` field points at this composed
module instead of the raw page file, so the dev server and the
bundler load the wrapped version automatically.

The layout discovery + composition logic lives in
`devserver/layouts.py:27-220`. When you add or remove a `layout.pyx`,
the file watcher detects the change and rebuilds every route under
that directory's subtree.

A `layout.pyx` looks like a regular page, but its component receives
a `children` prop instead of `data`:

```python
# pages/layout.pyx
@server
async def load_root_layout(request):
    return {"appName": "MyApp"}


import React from 'react';

export default function RootLayout({ data, children }) {
    return (
        <html lang="en">
            <body>
                <header>{data.appName}</header>
                <main>{children}</main>
            </body>
        </html>
    );
}
```

The layout *can* have its own `@server` loader — it runs in addition
to the page's loader, and its data is available to the layout
component via the `data` prop. (The page component still gets its own
`data`.)

### Templates: layouts that don't persist

A `template.pyx` is like a `layout.pyx` but with one key difference:
**templates remount on every navigation**. A layout keeps its DOM
and React state across navigation; a template throws everything away
and rebuilds.

This matters for things like animations that should restart on
every page change, or analytics that should fire once per page view.
Use `template.pyx` for "stateless wrapper around the page" and
`layout.pyx` for "persistent shell that survives navigation."

---

## Error boundaries

A `error.pyx` file at any level catches errors raised by descendants.
When a loader raises `LoaderError("not found", status_code=404)`, or
when a component throws during SSR, Pyxle walks up the tree from the
current route looking for the nearest `error.pyx` and renders it.

```
pages/
├── error.pyx                    ← root error boundary, catches everything
├── index.pyx
└── orgs/
    ├── error.pyx                ← scoped to /orgs/* routes
    └── [org]/
        └── settings.pyx
```

If `/orgs/acme/settings`'s loader raises, Pyxle first tries
`pages/orgs/error.pyx`. If that also fails (or doesn't exist), it
falls back to `pages/error.pyx`. If neither exists, it falls back to
the framework's default error document.

The error boundary component receives the error context as a prop:

```python
# pages/error.pyx
import React from 'react';

export default function ErrorBoundary({ error }) {
    return (
        <main>
            <h1>{error.message}</h1>
            <pre>{error.statusCode}</pre>
        </main>
    );
}
```

In dev mode, the error boundary also receives the Python traceback
in `error.traceback` for debugging. In production this is omitted —
production responses must not leak internal state.

The boundary discovery logic lives in
`devserver/error_pages.py`.

---

## Not-found boundaries

A `not-found.pyx` file is the same idea, scoped to 404 responses.
When a request hits Pyxle and no route matches, the framework walks
up from the request path looking for the nearest `not-found.pyx`:

```
pages/
├── not-found.pyx                ← root 404 page
└── docs/
    ├── not-found.pyx            ← custom 404 for /docs/* routes
    └── getting-started.pyx
```

A request for `/docs/nope` first tries `/docs/not-found.pyx`. A
request for `/random` falls through to `/not-found.pyx`. If neither
exists, the framework returns a plain 404 response.

---

## API routes

Pages are JSX-rendered HTML. **API routes** are pure JSON endpoints
under `pages/api/`. They use plain `.py` files (not `.pyx`) because
they have no client component:

```
pages/
└── api/
    ├── health.py                →  GET /api/health
    ├── users.py                 →  /api/users  (any HTTP method)
    └── users/
        └── [id].py              →  /api/users/{id}
```

An API route module exports an async function with a name matching
the HTTP method:

```python
# pages/api/health.py
async def get(request):
    return {"status": "ok"}

async def post(request):
    body = await request.json()
    return {"received": body}
```

The dev server inspects the module at registration time, finds the
`get`, `post`, etc. functions, and registers a Starlette endpoint
for each. There's no decorator — the function name *is* the contract.

If a single function should handle multiple methods, name it
`handle` instead and Pyxle routes all methods to it:

```python
async def handle(request):
    if request.method == "GET":
        return {"data": "..."}
    elif request.method == "POST":
        ...
```

API routes can use the same dynamic segment syntax as pages
(`[id].py`, `[...slug].py`, etc.).

---

## Action routes

`@action`-decorated functions inside a `.pyx` page get their own
endpoint at `/api/__actions/{action_name}`. This is invisible — you
never write the URL — but it's how the client-side `useAction()` hook
talks to the server.

For example, given:

```python
# pages/dashboard.pyx
@server
async def load(request):
    return {"count": 0}

@action
async def increment(request):
    body = await request.json()
    return {"value": body["current"] + 1}

@action
async def reset(request):
    return {"value": 0}

# ... JSX ...
```

…the dev server registers:

- `/dashboard` → page handler (loader + component render)
- `/api/__actions/increment` → action handler (POST only)
- `/api/__actions/reset` → action handler (POST only)

The client-side `useAction('increment')` hook returns a function that
POSTs to the `/api/__actions/increment` URL with whatever payload you
pass it. The action returns its result as JSON.

Action names must be **unique within a page** (the parser enforces
this). Across pages, names can collide — but each `.pyx` file
registers its actions independently, so the routing is per-page.

Action routing lives in `devserver/starlette_app.py:363-484`.

---

## How a request finds its handler

When Starlette receives a request, here's what happens (simplified):

1. **Static asset middleware** checks if the path starts with
   `/client/`, `/dist/`, or matches a file in `public/`. If so,
   serve the file directly without invoking any Pyxle handlers.

2. **CORS / CSRF middleware** runs (if configured).

3. **Vite proxy middleware** (dev only) checks if the path matches
   a Vite-served asset (`.js`, `.css`, `/@vite/*`, `/@react-refresh`).
   If so, proxy to Vite's port.

4. **Page router** looks up the path in the route table. If found,
   call the page handler:
   - If `x-pyxle-navigation: 1` header is set, return a JSON nav
     response (loader data + head markup).
   - Otherwise, return a streaming HTML response (full SSR).

5. **API router** dispatches `/api/*` requests (excluding action
   routes) to the matching `pages/api/*.py` handler.

6. **Action router** dispatches `/api/__actions/*` requests to the
   matching `@action` function in the relevant page.

7. **Catch-all 404 handler** walks up the request path looking for
   the nearest `not-found.pyx`. Renders it if found, otherwise
   returns a plain 404.

The order matters: static files are served before any dynamic
handler runs, and action routes are dispatched before the generic
API router so an `@action` named `users` doesn't collide with a
`pages/api/users.py` file.

Source: `devserver/starlette_app.py:506-735`.

---

## The route table

At startup (and after every rebuild), the dev server builds a single
in-memory `RouteTable` object containing every page, API, and
action route discovered in the project:

```python
@dataclass(frozen=True)
class RouteTable:
    pages: tuple[PageRoute, ...]
    apis: tuple[ApiRoute, ...]
    actions: tuple[ActionRoute, ...]
```

Each `PageRoute` has all the paths the SSR pipeline needs to render
it (server module path, client module path, metadata path, route
path, loader name, head metadata, etc.). The dev server builds the
Starlette router by iterating these tuples and registering one
Starlette `Route` per entry.

The route table is **frozen and rebuilt on changes** — it's never
mutated in place. When the file watcher detects a change, the
incremental builder produces a new metadata file, the registry
rebuilds the route table, and the dev server swaps it in atomically.

---

## Where to read next

- **[The dev server](dev-server.md)** — How the route table gets
  built, how the Starlette router uses it, how the file watcher
  triggers rebuilds, and how the WebSocket overlay reports errors.

- **[Server-side rendering](ssr.md)** — What happens *inside* a
  page handler: loader execution, head merging, component rendering,
  and document assembly.

- **[The compiler](compiler.md)** — Where the metadata that powers
  the route table comes from.
