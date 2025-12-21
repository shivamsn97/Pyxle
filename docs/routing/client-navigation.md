# Client Navigation + `<Link>`

Pyxle ships a minimal SPA router so moving between pages feels instant without giving up server-rendered HTML. The runtime code is generated inside `.pyxle-build/client/runtime/` by `pyxle/devserver/client_files.py`.

## How it works

1. `pyxle dev` writes `client-entry.js` that calls `import.meta.glob('/pages/**/*.jsx')` to lazily load compiled page components.
2. `window.__PYXLE_PAGE_PATH__` and `window.__PYXLE_PAGE_DATA__` are set by the server response.
3. The client router listens for `popstate`, intercepts `<a>` clicks, and fetches navigation payloads from Starlette by sending `x-pyxle-navigation: 1` headers.
4. Starlette returns JSON containing `{ html, data, head, status }` via `build_page_navigation_response()` so the client can swap the DOM subtree without reloading assets.

## Using `<Link>`

Import from `pyxle/client` (exposed via the generated runtime). Example from the scaffolded home page:

```jsx
import { Link } from 'pyxle/client';

<Link href="/api/pulse" className="rounded-2xl border px-4 py-3">View API pulse →</Link>
```

- `prefetch="hover"` (default) kicks off a navigation request when the link is hovered.
- Set `replace` to avoid pushing to history.
- External URLs (`href` starting with `http`) fall back to normal anchors.

## Compare with Next.js

- Similar to Next.js `next/link` + the app router's fetch cache. Pyxle does not have segments or partial renders yet, so each navigation fetches the full HTML/JSON payload for the destination page.
- There is no React Server Component boundary; the navigation payload already contains fully rendered HTML plus the props for hydration.

Related docs:
- [Loader lifecycle](../fundamentals/loader-lifecycle.md)
- [Overlay & watchers](../devserver/overlay-and-watchers.md) for how navigation failures surface during development.
