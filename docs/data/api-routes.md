# API Routes

Any `.py` file under `pages/api/` becomes a Starlette route. The dev server copies the module into `.pyxle-build/server/pages/api/` and mounts it under `/api/*`.

```python
# pages/api/pulse.py
from datetime import datetime, timezone
from starlette.responses import JSONResponse
from pyxle import __version__

@server
async def build_pulse_payload():
    ...

async def endpoint(request):
    payload = build_pulse_payload()
    return JSONResponse(payload)
```

## Handler resolution

`pyxle/devserver/starlette_app.py` looks for:

1. `endpoint` callable → used directly (function or async function).
2. Otherwise, the first subclass of `starlette.endpoints.HTTPEndpoint`.

If neither is found, Pyxle raises `ApiRouteError` during import so you see the failure immediately.

## HTTP methods

- Function-based handlers can inspect `request.method` and branch manually.
- HTTPEndpoint subclasses can implement `get`, `post`, etc.
- All standard methods (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`) are wired automatically.

## Shared helpers

Because API modules live in the same repo as loaders, you can import shared services, models, or configuration without dealing with HTTP serialization. Use them to expose diagnostics or webhooks while keeping your React pages purely presentational.

## Compare with Next.js

These mirror Next.js `pages/api/*` routes, but they run on Starlette instead of Node. Use them when loader data is not enough (e.g., webhook receivers, long-poll endpoints, or `curl` diagnostics like the scaffolded `/api/pulse`).

See [Custom middleware & route hooks](middleware-hooks.md) for attaching cross-cutting concerns.
