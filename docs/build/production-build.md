# Production Build Pipeline

`pyxle build` compiles everything into a deployable `dist/` directory. Under the hood it calls `pyxle.build.run_build()` (see `pyxle/build/pipeline.py`).

## Steps

1. **Warm build cache** – `build_once(settings, force_rebuild=True)` recompiles `pages/`, copies API modules, syncs client assets, layouts, and metadata.
2. **Assemble distribution folders** – Existing `dist/` is removed, then:
   - `.pyxle-build/server` → `dist/server`
   - `.pyxle-build/client` (bootstrap + per-page bundles) → `dist/client`
   - `.pyxle-build/metadata` → `dist/metadata`
   - `public/` → `dist/public`
3. **Run Vite** – `pyxle/build/vite.py` runs `vite build` with the generated client entry, then returns the manifest path.
4. **Page manifest** – `build_page_manifest()` combines the metadata registry with Vite output so the SSR runtime knows which hashed assets belong to each route. Result is written to `dist/page-manifest.json`.

## Output

```
dist/
├── client/          # Vite build (hashed JS/CSS)
├── server/          # Python modules served by Starlette/Uvicorn
├── metadata/        # JSON descriptors (head, layouts)
├── public/          # Copied static assets
└── page-manifest.json
```

## Command options

```
pyxle build --out-dir ./build-output --config alt.config.json --no-incremental
```

- `--out-dir` sets a custom distribution directory.
- `--config` points to a different `pyxle.config.json`.
- `--incremental` reuses cache artifacts when true (default false for clean builds).

## Compare with Next.js

This mirrors `next build`, but splits the output between Python (server) and Vite (client). You are responsible for serving both halves—see [`pyxle serve`](serve-command.md).

Before running the build, ensure you also run `npm run build:css` so Tailwind output is up to date.

### Verify builds locally

```sh
pyxle build --out-dir ./dist && PYXLE_ENV=production pyxle serve --skip-build
```

Smoke-test dynamic routes, API endpoints, and navigation locally before shipping the artifacts to CI/CD.

---
**Navigation:** [← Previous](index.md) | [Next →](serve-command.md)
