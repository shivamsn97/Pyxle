# Layouts and Slots

Layouts work the same way as in Next.js: drop `pages/layout.pyx` (or nested `layout.pyx` files) and export a default component that renders `{ children }`. Pyxle also supports optional slots so pages can expose extra mount points.

```pyx
# pages/layout.pyx
import React from 'react';

export const slots = {};
export const createSlots = () => slots;

export default function AppLayout({ children }) {
    return <div className="min-h-screen bg-slate-50">{children}</div>;
}
```

### How layout composition works

1. `pyxle/devserver/layouts.py` scans for `layout.pyx` files and writes synthetic React components that wrap each page component.
2. During SSR, `pyxle/ssr/template.py` includes the composed layout markup in the HTML shell.
3. Client-side, `client-entry.js` mirrors the same composition so hydration matches the server output.

### Slots

- Export `createSlots` and `slots` from a layout.
- Pages can import `createSlots()` from their layouts to fill named slots.
- Pyxle does not yet have a `<Slot />` component like Next.js; it uses the exported object to mount fragments.

### Nested layouts

Place another `layout.pyx` inside a route segment folder:

```
pages/
├── layout.pyx            # wraps everything
└── dashboard/
    ├── layout.pyx        # wraps dashboard routes only
    └── index.pyx
```

The compiler records layout relationships in `.pyxle-build/metadata/pages/**/*.json` so both the SSR renderer and client runtime share the same tree.

### Compare with Next.js

- Very similar to the Next.js `app/` router: layouts wrap child segments automatically.
- Pyxle does not yet support `loading.js` or `error.js` equivalents; use Starlette middleware and the overlay for now.

Next: [Client navigation](client-navigation.md) to see how the SPA router hops between layout-wrapped pages without full reloads.
