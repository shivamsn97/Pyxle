# Shared Layout and Head Primitives

Pyxle ships a couple of pragmatic building blocks inside every freshly scaffolded
project so you do not have to reinvent a navigation bar or copy/paste meta tag
logic every time you add a new page. The files live under `pages/components/`
and are regular Python or JavaScript modules, which means you can edit them like
any other part of your app.

## `pages/components/head.py`

```python
from pages.components import build_head

HEAD = build_head(
    title="My Pyxle Site",
    description="Async Python loaders meet React SSR.",
    extra=["<meta property=\"og:image\" content=\"/og.png\" />"],
)
```

`build_head()` escapes every string and returns a list of `<head>` fragments the
compiler already knows how to insert. You can keep using the helper in every
page or roll your own if you need a more advanced setup.

## `pages/components/layout.jsx`

```jsx
import { RootLayout, Link } from './components/layout.jsx';

export default function Page({ data }) {
  return (
    <RootLayout>
      <section>
        <h1>Hello, world</h1>
        <Link href="/components/demo" variant="primary">Components</Link>
      </section>
    </RootLayout>
  );
}
```

The scaffold exports:

- **`RootLayout`** – wraps every page in a styled shell with a navigation bar and
  footer. Drop your page content inside the `children` slot and keep iterating.
- **`Link`** – lightweight anchor component that picks the right styling variant
  (`ghost` by default, `primary` for call-to-action buttons) and automatically
  applies safe defaults for external links.
- **`SectionLabel`** – convenience component used on the homepage hero grid. It
  keeps typography consistent when you add additional sections.

All of these are regular React components: feel free to inline your own CSS or
swap them out entirely. They only exist to give brand-new projects a leg up and
show how to co-locate reusable JSX next to `.pyx` pages.

## Where to go next

- Want to share hooks/utilities? Create more files inside `pages/components/`
  and import them from any `.pyx` module.
- Need multiple layouts? Duplicate `RootLayout` or create `DashboardLayout`
  variants and wrap different routes manually until route groups land in a
  future release.
- Remember to update `HEAD` blocks when you change branding so social previews
  remain accurate.
