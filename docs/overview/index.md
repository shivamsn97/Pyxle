# Overview

Kick things off by understanding what Pyxle is and how a project is structured. Treat this section as your briefing before you open the editor.

## You will learn

- Why Pyxle keeps loaders (Python) and components (React) together.
- How the scaffolded project is laid out (pages, public assets, config files).
- Which commands (`pyxle init`, `pyxle dev`) you need for a brand-new app.

## Quick start recap

```bash
pyxle init acme-portal --install
cd acme-portal
npm run dev:css  # In a separate terminal, keep Tailwind watching
pyxle dev
```

Once the dev server is running, open `http://127.0.0.1:8000` and modify `pages/index.pyx`. The watcher will recompile the page and the browser overlay will confirm the rebuild.

## Pages in this section

1. [What is Pyxle?](what-is-pyxle.md) – A mental model for the platform and how it compares to Next.js.
2. [Project structure](project-structure.md) – A tour of the scaffold so you know where to add routes, APIs, and assets.

---
**Navigation:** [← Previous](../README.md) | [Next →](what-is-pyxle.md)
