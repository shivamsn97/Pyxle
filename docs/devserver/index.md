# Dev Server

`pyxle dev` keeps your local workflow tight: it compiles pages, proxies Vite, watches files, and streams overlay updates.

## You will learn

- What happens during startup (config merge, first build, watcher boot).
- How Starlette, Vite, and the overlay channel fit together.
- How to reason about logs, health endpoints, and rebuild summaries.

## CLI refresher

```bash
pyxle dev --host 0.0.0.0 --port 9000 --print-config
```

## Pages in this section

1. [How the dev server works](dev-server.md)
2. [Overlay, watcher, and diagnostics](overlay-and-watchers.md)

---
**Navigation:** [← Previous](../runtime/pyxle-client.md) | [Next →](dev-server.md)
