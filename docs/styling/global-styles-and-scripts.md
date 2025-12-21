# Global Styles & Scripts

Need to load fonts, analytics, or shared CSS on every page? Configure them in `pyxle.config.json` and Pyxle will copy/watch them like any other source file.

```json
{
  "styling": {
    "globalStyles": ["pages/styles/tailwind.css", "pages/styles/theme.css"],
    "globalScripts": ["pages/scripts/analytics.js"]
  }
}
```

## How it works

- `pyxle/config.py` validates the entries, ensuring they are strings.
- `pyxle/devserver/styles.py` and `scripts.py` resolve the absolute paths, copy them into `.pyxle-build/client/global/{styles,scripts}` and emit metadata used by the client bootstrap.
- The dev watcher (`pyxle/devserver/watcher.py`) monitors the parent directories so edits trigger rebuilds.
- During SSR, `pyxle/ssr/template.py` injects `<link>` and `<script>` tags referenced by the generated metadata.

Global scripts run in the browser. Use them for analytics beacons, feature flags, or other DOM side effects. Keep middleware/server-only logic in Python modules instead.

## Compare with Next.js

This is similar to importing CSS at the root layout or using `_app.tsx`, but explicitly configured so the dev server can watch files outside `pages/`. The advantage is zero runtime import costs—the files are copied and linked ahead of time.

Pair this with [Tailwind workflow](tailwind.md) for a complete styling setup.

### Practical uses

- Add font preloads by listing `public/fonts/ibm-plex.woff2` under `globalStyles` and referencing it via `@font-face`.
- Ship analytics safely: place your snippet under `pages/scripts/analytics.js` and keep secrets server-side by reading them from environment variables during SSR.
- For design systems, register `globalScripts` that set up `window.theme` before React hydrates.

---
**Navigation:** [← Previous](tailwind.md) | [Next →](../runtime/index.md)
