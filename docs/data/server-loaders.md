# Server Loaders

Loaders are async Python functions decorated with `@pyxle.server`. They run on Starlette for every request and provide props for the React component.

```py
from pyxle import server
from starlette.responses import RedirectResponse

@server
async def load_profile(request):
    user = await current_user(request)
    if not user:
        raise RedirectResponse("/login")
    return {"user": user.dict(include={"name", "email"})}
```

## Contract enforced by the parser

- Declared with `@server` from `pyxle/runtime.py`.
- Async only, module scope, first argument named `request`.
- Return options:
  - `dict` → `data` props, HTTP 200.
  - `(dict, status_code)` → HTTP status overridden.

The compiler stores loader metadata in `.pyxle-build/metadata/pages/<route>.json`, including parameter names and whether the HEAD is dynamic.

## Access to Starlette APIs

Because Pyxle loads your module directly, you can import anything, manage database sessions, or call other parts of your project. The `request` object exposes:

- `request.path_params`
- `request.query_params`
- `await request.json()` / `.form()`
- `request.state` for middleware-provided data

## Error handling

- Exceptions bubble up to `pyxle/devserver/overlay.py`, which broadcasts an overlay event and shows the stack trace in the browser.
- In production, Starlette returns a JSON error (API routes) or the HTML error template (pages), matching Starlette defaults.

## Compare with Next.js

- Equivalent to `export async function GET()` or `generateMetadata`, except you stay in Python.
- No separate `getServerSideProps` or `getStaticProps`; Pyxle currently renders everything dynamically.

Continue with [API routes](api-routes.md) to build REST endpoints alongside page loaders.
