# Overlay, Watchers, and Diagnostics

Pyxle's dev experience is modeled after Next.js fast refresh + error overlays, but implemented with Starlette primitives.

## File watching

- `pyxle/devserver/watcher.py` uses Watchdog to monitor `pages/`, `public/`, and any directories referenced by `globalStyles` / `globalScripts`.
- Events are debounced (default 250 ms) so saving multiple files triggers one rebuild.
- After each rebuild, the watcher logs a summary (compiled pages, copied APIs, synced assets) and invalidates Python import caches so reloading works without restarting Uvicorn.

## Overlay websocket

- `OverlayManager` (see `pyxle/devserver/overlay.py`) manages browser clients over WebSocket.
- When loaders or API routes raise exceptions, `build_page_response()` or the Starlette exception handler calls `overlay.notify_error(...)` with the stack trace.
- Once the error clears on the next successful render, `notify_clear()` dismisses the overlay.
- File changes trigger `notify_reload()` so the client knows when to refresh modules.

## Browser integration

`pyxle/devserver/client_files.py` injects a small client script that:

1. Opens a WebSocket to `/__pyxle__/overlay`.
2. Renders stack traces in a styled overlay when it receives `error` events.
3. Clears itself on `clear` events and triggers a soft reload on `reload` events.

## Diagnostics endpoint

The scaffolded `/api/pulse` route demonstrates how to expose project health data. Use it to monitor versions, uptime, or feature flags while building.

## Compare with Next.js

- Similar to Next.js overlay + Fast Refresh, but driven by Watchdog + Starlette instead of webpack + React Refresh.
- Because Python rebuilds are not hot-swapped the same way as JS, Pyxle invalidates modules and re-imports them, which is usually enough for stateless loaders.

Troubleshooting tips:

- If the overlay disconnects repeatedly, ensure nothing else is proxying the `/__pyxle__` routes.
- For heavy file trees, increase the debounce interval via `ProjectWatcher(debounce_seconds=...)` (requires custom dev server entrypoint for now).
