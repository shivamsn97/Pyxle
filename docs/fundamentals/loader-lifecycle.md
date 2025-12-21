# Loader ↔ Component Lifecycle

Pyxle keeps the request lifecycle simple:

1. Starlette receives a request for `/foo`.
2. `pyxle/devserver/routes.py` maps the URL to a compiled page module.
3. The generated module imports your `@server` loader (if present) and executes it with the Starlette `Request` object.
4. Loader return value becomes `data` props. If you return `(payload, status_code)`, the HTTP status is overridden.
5. The SSR runtime (`pyxle/ssr/renderer.py`) renders the React component with `{ data }` and inline styles.
6. During hydration, the client bundle re-runs the same component with `window.__PYXLE_PAGE_DATA__`.

```python
# generated server stub (simplified)
from pages.foo import load_page
from pyxle.ssr import build_page_response

async def endpoint(request):
    loader_result = await load_page(request)
    return await build_page_response(request, settings, page=metadata, renderer=component_renderer)
```

### Status codes and redirects

- Return `(payload, 201)` to change the status.
- Raise `starlette.responses.RedirectResponse` from your loader if you need a redirect; Pyxle does not intercept it.

### Accessing query/body data

Loaders receive `starlette.requests.Request`, so you can use `.query_params`, `.json()`, `.form()`, or `.state`. There is no custom wrapper.

### Loader errors ↔ overlay

Uncaught exceptions propagate to `pyxle/devserver/overlay.py`, which broadcasts the stack trace to the browser overlay while Starlette still returns a styled error page. Fix the code and the watcher will rebuild plus dismiss the overlay.

## Compare with Next.js

- Equivalent to `export async function GET()` + `export default function Page({ params, searchParams })`. Pyxle currently passes only `request`, so parse params from `request.path_params` or `request.query_params` (Starlette APIs).
- There is no Suspense boundary between loader and component—fetch in Python, not in the component.

Next: [File-based routing](../routing/file-based-routing.md) to see how loaders are wired to URLs.
