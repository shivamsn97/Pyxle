# Dynamic Segments & Catch-alls

Dynamic filenames are converted into Starlette path parameters. The heavy lifting happens in `pyxle/routing/paths.py`.

| Filename | Route | `request.path_params` |
| --- | --- | --- |
| `pages/posts/[id].pyx` | `/posts/{id}` | `{ "id": "123" }` |
| `pages/shop/[category]/[product].pyx` | `/shop/{category}/{product}` | `{ "category": "shirts", "product": "oxford" }` |
| `pages/docs/[...slug].pyx` | `/docs/{slug:path}` | `{ "slug": "guides/routing" }` |
| `pages/docs/[[...slug]].pyx` | `/docs` (primary) + `/docs/{slug:path}` alias | `{}` or `{ "slug": "a/b" }` |

### Implementation details

- `_parse_dynamic` wraps `[name]` segments in `{name}`.
- `_parse_catchall` converts `[...slug]` into `{slug:path}` so Starlette handles slashes.
- `_parse_optional_catchall` adds an alias: the primary path remains `/docs`, the alias registers `/docs/{slug:path}`.
- Parameter names are sanitised: `[foo-bar]` → `{foo_bar}`.

### Accessing params

Loaders receive `request.path_params` straight from Starlette:

```python
@server
async def load_post(request):
    post_id = request.path_params["id"]
    return {"post": await get_post(post_id)}
```

### Testing param plumbing

```python
from starlette.requests import Request

@server
async def load_category(request: Request):
    params = request.path_params
    if params.get("category") not in {"shirts", "shoes"}:
        raise HTTPException(status_code=404)
    return {"category": params["category"]}
```

Pair this with manual smoke checks (for example, `curl http://localhost:8000/shop/shirts`) or your existing browser automation scripts to keep regressions from sneaking in when renaming folders.

### Compare with Next.js

Identical to `app/blog/[slug]/page.tsx` or `app/docs/[...slug]/page.tsx`. Optional catch-alls behave like Next.js `[[...slug]]` when you need both `/docs` and `/docs/*` handled by the same file.

See [Layouts & slots](layouts-and-slots.md) to understand how nested routes compose.

---
**Navigation:** [← Previous](file-based-routing.md) | [Next →](layouts-and-slots.md)
