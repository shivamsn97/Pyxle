# Styling

Give your pages polish with Tailwind and project-wide assets.

## You will learn

- How the scaffolded Tailwind pipeline works (`pages/styles/tailwind.css` → `public/styles/tailwind.css`).
- Adding additional CSS or JS files via `pyxle.config.json` `styling` block.
- Tips for organizing design tokens and dark mode.

## Sample config

```jsonc
{
  "styling": {
    "globalStyles": ["pages/styles/tailwind.css", "pages/styles/theme.css"],
    "globalScripts": ["pages/scripts/analytics.js"]
  }
}
```

## Pages in this section

1. [Tailwind workflow](tailwind.md)
2. [Global styles & scripts](global-styles-and-scripts.md)

---
**Navigation:** [← Previous](../data/middleware-hooks.md) | [Next →](tailwind.md)
