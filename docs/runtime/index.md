# Runtime

Understand what runs in the browser after SSR completes.

## You will learn

- Managing `<head>` tags via the `HEAD` constant and how they diff during navigation.
- How the generated `pyxle/client` runtime hydrates pages, handles prefetching, and exposes router helpers.
- Hooks for working with slots, theme toggles, and other UI state.

## Example: updating document title in a loader

```py
HEAD = ["<title>Dashboard • Pyxle</title>"]
```

## Pages in this section

1. [Head management](head-management.md)
2. [Pyxle client runtime](pyxle-client.md)

---
**Navigation:** [← Previous](../styling/global-styles-and-scripts.md) | [Next →](head-management.md)
