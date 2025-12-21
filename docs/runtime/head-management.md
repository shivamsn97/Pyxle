# Head Management

Pyxle keeps head tags declarative. Assign a `HEAD` variable inside your `.pyx` file and the compiler captures it.

```py
HEAD = """
<title>Pyxle • Next-style starter</title>
<meta name="description" content="Kick off a Pyxle project" />
<link rel="stylesheet" href="/styles/tailwind.css" />
"""
```

## Parsing rules

- Literal string or list of strings → stored as-is.
- Any dynamic expression (e.g., function call, f-string using variables) marks the head as dynamic; the runtime evaluates it when rendering.
- Metadata lives in `.pyxle-build/metadata/pages/<route>.json` and is fed into `pyxle/ssr/template.py`.

## Injection order

1. Global styles/scripts from config.
2. Page-specific `HEAD` entries.
3. Dev server extras (overlay client, Vite HMR) when `debug=True`.

Because Pyxle renders HTML via `pyxle/ssr/template.DocumentTemplate`, everything ends up inside `<head>` before the response is streamed to the browser.

## Compare with Next.js

This replaces `export const metadata = { ... }` or `<Head>` usage. The difference is that Pyxle does not diff head tags on the client; instead, it re-renders the full head during navigation using the metadata manifest. When you request navigation payloads (`x-pyxle-navigation: 1`), the response includes both HTML and head snippets so the client router can patch document metadata.

Need to expose page-specific JSON-LD or Open Graph tags? Add them to `HEAD` or compute them inside the loader and string-format the result.

### Dynamic head example

```pyx
from pyxle import server

@server
async def load_product(request):
	product = await fetch_product(request.path_params["id"])
	return {"product": product}

def HEAD(data):
	product = data["product"]
	return f"""
	<title>{product['name']} • Pyxle Shop</title>
	<meta property="og:image" content="{product['image']}" />
	"""
```

Returning a callable lets you reuse loader data instead of recomputing API calls.

---
**Navigation:** [← Previous](index.md) | [Next →](pyxle-client.md)
