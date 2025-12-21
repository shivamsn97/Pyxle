# Data & Middleware

Once routing is in place, add real data sources and cross-cutting behaviour.

## You will learn

- Loader best practices (handling params, using `httpx`, returning status codes).
- Building Starlette-compatible API routes for webhooks or AJAX calls.
- Attaching middleware and route hooks for auth, logging, or CSP.

## Data-layer starter kit

```py
# pages/api/profile.py
from starlette.responses import JSONResponse

async def endpoint(request):
    user = await request.state.auth.require_user()
    return JSONResponse({"name": user.name, "email": user.email})
```

## Pages in this section

1. [Server loaders](server-loaders.md)
2. [API routes](api-routes.md)
3. [Custom middleware & route hooks](middleware-hooks.md)

---
**Navigation:** [← Previous](../routing/client-navigation.md) | [Next →](server-loaders.md)
