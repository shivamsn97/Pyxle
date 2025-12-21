# Deploying Pyxle Apps

All deployments follow the same recipe:

1. Build CSS + client assets (`npm run build:css`).
2. Run `pyxle build` to produce `dist/`.
3. Host the Starlette app (`pyxle serve` or custom ASGI server).
4. Expose static assets (`dist/public` and `dist/client`) via the app or a CDN.

## Container-friendly workflow

```Dockerfile
FROM node:20-slim AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install
COPY pages/ pages/
RUN npm run build:css

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY --from=assets /app/public/styles ./public/styles
COPY . ./
RUN pyxle build

CMD ["pyxle", "serve", "--host", "0.0.0.0", "--port", "8000", "--skip-build"]
```

## Static assets

- Default: `pyxle serve` mounts `dist/public` at `/` and `dist/client` at `/client`.
- CDN option: run `pyxle serve --no-serve-static` and upload both folders to object storage. Configure your reverse proxy to rewrite `/client/*` to the CDN URL.

## Scaling

`pyxle serve` runs uvicorn in single-process mode. For more throughput:

```bash
uvicorn pyxle_entrypoint:app --workers 4 --host 0.0.0.0 --port 8000
```

Where `pyxle_entrypoint.py` contains:

```python
from pyxle.cli import create_starlette_app
from pyxle.devserver import DevServerSettings
from pyxle.build.manifest import load_manifest
from pyxle.devserver.registry import build_metadata_registry
from pyxle.devserver.routes import build_route_table

settings = DevServerSettings.from_project_root(...)
settings = settings.replace(debug=False, page_manifest=load_manifest("dist/page-manifest.json"))
registry = build_metadata_registry(settings)
route_table = build_route_table(registry)
app = create_starlette_app(settings, route_table, serve_static=False)
```

## Environment variables

- Ports/hosts are configured via CLI flags or config file.
- Use `.env` + `os.environ` inside loaders for secrets; Pyxle does not inject env vars automatically.

## Compare with Next.js

Instead of `next start`, you own the ASGI process, which makes it straightforward to deploy on Fly.io, Railway, Render, AWS App Runner, or any platform that supports Python 3.11 + Node 18/20 for asset builds.

Checklist:

- [ ] `npm run build:css`
- [ ] `pyxle build`
- [ ] Serve `dist/` via `pyxle serve` or custom ASGI host
- [ ] Point reverse proxy/CDN at `/client` + `/public`
