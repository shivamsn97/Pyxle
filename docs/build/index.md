# Build & Serve

When you're ready to ship, `pyxle build` compiles everything into `dist/` and `pyxle serve` hosts the result.

## You will learn

- How incremental builds leverage `.pyxle-build/` caches.
- What the `page-manifest.json` does and how SSR consumes it.
- Ways to run the production server locally before deploying.

## Quick commands

```bash
npm run build:css
pyxle build --out-dir ./dist --incremental
pyxle serve --host 0.0.0.0 --port 8080 --skip-build
```

## Pages in this section

1. [Production build pipeline](production-build.md)
2. [`pyxle serve` command](serve-command.md)

---
**Navigation:** [← Previous](../devserver/overlay-and-watchers.md) | [Next →](production-build.md)
