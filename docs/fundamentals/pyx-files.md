# Authoring `.pyx` Files

A `.pyx` file pairs three concerns that ship together so you never lose track of where data, document metadata, and UI live:

1. Optional module-level constants (e.g., `HEAD`).
2. An async server loader decorated with `@server`.
3. A default React component export.

The parser in `pyxle/compiler/parser.py` walks the file once, classifies each line as Python or JSX, and emits separate artifacts. The compiler enforces the contract so runtime failures show up at build time.

```pyx
from datetime import datetime, timezone
from pyxle import __version__
from pyxle import server

HEAD = [
    "<title>Pyxle • Next-style starter</title>",
    "<meta name=\"description\" content=\"Kick off...\">",
]

@server
async def load_home(request):
    now = datetime.now(tz=timezone.utc)
    return {"timestamp": now.isoformat(), "version": __version__}

import React from 'react';

export default function Page({ data }) {
    return <pre>{JSON.stringify(data)}</pre>;
}
```

## Loader rules enforced by the compiler

- Must be `async def` at module scope.
- The first parameter must be named `request` (`pyxle/compiler/parser.py` raises otherwise).
- Exactly one `@server` loader per file.
- Return value can be `dict` or `(dict, status_code)`; this is validated later when Starlette serialises the response.

## JSX section rules

- Standard ES modules: import React, hooks, or helpers from `pyxle/client`.
- Default export must be a React component that accepts `{ data }` props (the loader payload) plus optional `slots`.
- Named exports like `createSlots` or `slots` are passed through untouched.

## Python + React tips

- Install any HTTP client or ORM you prefer. Common pattern:

    ```py
    import httpx

    @server
    async def load_posts(request):
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("https://example.com/api/posts")
            resp.raise_for_status()
            return {"posts": resp.json()}
    ```

- Client side you can use every React hook, Suspense boundary, or context provider exactly as in a regular Vite project. Co-locate UI helpers by creating sibling files (e.g., `pages/posts/components/PostList.jsx`) and import them normally.
- Need slots? Export `export const slots = ['header', 'main'];` and Pyxle passes `slots.header` to your component. Layout examples live in [Routing → Layouts](../routing/layouts-and-slots.md).

## HEAD management

If you define `HEAD`, the parser stores literal strings under `parse_result.head_elements`. During SSR, `pyxle/ssr/template.py` injects these tags into the document head. Dynamic assignments (e.g., computed arrays) are still allowed, but they mark the head as "dynamic" so the runtime evaluates it per request.

## Compare with Next.js

- Equivalent to co-locating `generateMetadata`, `generateStaticParams`, and the React component in one file.
- Instead of React Server Components, Pyxle sends plain props via JSON and hydrates with React DOM just like Next.js pages router.

Continue with [Loader ↔ component lifecycle](loader-lifecycle.md) for how data flows between the Python and React halves.

---
**Navigation:** [← Previous](index.md) | [Next →](loader-lifecycle.md)
