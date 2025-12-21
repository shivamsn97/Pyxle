# Routing

Pyxle maps file paths to URLs automatically. This section shows how to create pages, dynamic segments, nested layouts, and seamless client-side navigation.

## You will learn

- Conventions for static routes, dynamic params, and catch-all segments.
- How to layer layouts/slots so nested content stays DRY.
- How the SPA router and `<Link>` component keep navigation instant.

## Example: blog route with layout

```
pages/
├── layout.pyx
└── blog/
    ├── layout.pyx
    ├── [slug].pyx
    └── index.pyx
```

```py
# pages/blog/[slug].pyx
@server
async def load_post(request):
    slug = request.path_params["slug"]
    post = await posts.get(slug)
    return {"post": post}
```

## Pages in this section

1. [File-based routing](file-based-routing.md)
2. [Dynamic segments & catch-alls](dynamic-segments.md)
3. [Layouts and slots](layouts-and-slots.md)
4. [Client navigation + `<Link>`](client-navigation.md)

---
**Navigation:** [← Previous](../fundamentals/loader-lifecycle.md) | [Next →](file-based-routing.md)
