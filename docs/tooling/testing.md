# Testing Status & Verification Tips

Pyxle does not bundle an official or opinionated test runner yet. Until the framework ships first-class tooling, rely on the same verification steps you already trust in your projects and focus on smoke-testing the supported Pyxle commands.

## Current recommendations

- Exercise `pyxle dev` while editing to confirm loaders, routes, and the SPA router behave as expected.
- Run `pyxle build` (optionally with `--incremental`) before you commit so compiler regressions surface early.
- Launch `pyxle serve --skip-build` against the freshly built `dist/` directory and hit critical routes with `curl` or your browser to ensure hashed assets resolve correctly.

## Lightweight automation ideas

### Loader/API smoke test

```python
import asyncio
from httpx import AsyncClient
from pyxle.devserver.starlette_app import create_starlette_app

async def verify_api(settings):
    app = create_starlette_app(settings)
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/pulse")
        response.raise_for_status()

asyncio.run(verify_api(settings))
```

Swap in whichever routes matter most to your app; this pattern ensures Starlette, middleware hooks, and loaders all execute without involving the dev server UI.

### Client checks

- Start `pyxle dev --host 0.0.0.0` and manually load pages on multiple devices/browsers.
- Use your preferred browser automation stack (for example, the tools you already run against other projects) pointed at the dev server. Pyxle does not add new requirements beyond serving HTML on port `8000`.

### CI outline

1. `pyxle install --python --node`
2. `npm run build:css`
3. `pyxle build`
4. Optional: `PYXLE_ENV=production pyxle serve --skip-build &` + health check `curl`
5. Publish the `dist/` artifacts when the health check passes.

Keep these steps in a shell script so you can reuse them locally and in CI without depending on a particular third-party test runner.

---
**Navigation:** [← Previous](langkit.md) | [Next →](../reference/index.md)
