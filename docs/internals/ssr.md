# SSR Renderer

Pyxle renders React components on the server by shelling out to Node, then streams HTML through Starlette. Core code lives in `pyxle/ssr/renderer.py` and `pyxle/ssr/template.py`.

## ComponentRenderer

- Maintains an in-memory cache mapping component paths to callable renderers.
- Default factory (`_default_factory`) wraps `_NodeComponentRuntime`, which spawns a Node subprocess pointing at `pyxle/ssr/render_component.mjs`.
- Props are JSON-serialised and piped to Node via `subprocess.run`.
- Output is parsed into `RenderResult` with HTML + inline style fragments.

## Document template

`pyxle/ssr/template.DocumentTemplate` assembles:

1. `<!doctype html>`
2. `<head>` containing global assets + page `HEAD` entries + overlay/Vite scripts (in dev).
3. `<body>` with the layout-wrapped HTML and hydration payloads injected into `window.__PYXLE_PAGE_DATA__` and `window.__PYXLE_PAGE_PATH__`.

## Streaming responses

`build_page_response()` returns a Starlette `Response` that streams HTML to the client. For SPA navigations, `build_page_navigation_response()` returns JSON describing the rendered HTML, head tags, and props so the client router can update without a full reload.

## Error paths

- Node runtime failures raise `ComponentRenderError` with parsed stderr output.
- Loader exceptions bubble up to the overlay and to Starlette's debug page in dev.
- Missing manifests during `pyxle serve` cause startup failures, preventing half-baked deployments.

## Compare with Next.js

Pyxle's SSR is closer to Next.js pages router (React DOM render-to-string) than to the app router (React Server Components). There is no Flight protocol; the entire result is HTML + JSON. Because the renderer is a subprocess, you can swap it for a custom implementation by passing a different factory to `ComponentRenderer` (useful for experimental renderers or pre-rendering workflows).

See [Production build](../build/production-build.md) to understand how hashed assets are wired into the manifest consumed by the renderer.

### Custom renderers

You can inject your own renderer:

```python
from pyxle.ssr.renderer import ComponentRenderer

renderer = ComponentRenderer(factory=my_factory)
```

Where `my_factory` returns callables that accept `(component_path, props)` and return `RenderResult`. This is handy for experimenting with streaming SSR or alternative runtimes.

---
**Navigation:** [← Previous](compiler.md) | [Next →](../README.md)
