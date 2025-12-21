# Pyxle Client Runtime

Compiled pages import helpers from `pyxle/client`. The bundle is generated automatically by `pyxle/devserver/client_files.py` and exposes a tiny API:

- `Link` – SPA-aware anchor component with prefetching.
- `navigate(url, { replace })` – Imperative navigation helper.
- `prefetch(url)` – Manually warm the navigation cache.
- `useNavigation()` – Subscribe to route changes (planned; exported when present).

## Anatomy

1. `client-entry.js` bootstraps React on `#pyxle-root` and reads `window.__PYXLE_PAGE_DATA__` produced by the server.
2. `routes-manifest.json` describes every page module, loader hash, head entries, and layout tree.
3. The router intercepts clicks, fetches `/target` with `x-pyxle-navigation: 1`, and expects a JSON payload from `build_page_navigation_response()`.
4. Once the payload arrives, the client updates `document.title`, swaps head tags, re-renders the React tree, and pushes/replace state.

## Prefetching

```jsx
<Link href="/dashboard" prefetch="hover">Dashboard</Link>
```

- `hover` (default) → issue navigation request when hovered.
- `visible` → prefetch when Link intersects the viewport.
- `false` → disable prefetching.

## Error handling

If a navigation request fails, the router surfaces the error via the overlay (dev) or falls back to a full page reload (production) to avoid broken states.

## Compare with Next.js

`pyxle/client` is closer to `next/navigation` + `next/link` from the app router, but implemented in a single entrypoint so it can run without Node features. Because Pyxle relies on Starlette for HTML + JSON responses, you get a streaming SSR path similar to Next.js `app` router without React Server Components.

See [Client navigation](../routing/client-navigation.md) for end-to-end flow diagrams.

### Practical extras

- Call `prefetch('/path')` inside `useEffect` hooks to warm key dashboards.
- Wrap imperative data refreshes around `navigate(window.location.pathname, { replace: true })` to simulate soft refreshes.
- The router stores `window.__PYXLE_ROUTER__`; advanced integrations can subscribe to its internal events (see `pyxle/devserver/client_files.py`).

---
**Navigation:** [← Previous](head-management.md) | [Next →](../devserver/index.md)
