# Tailwind Workflow

Pyxle ships with Tailwind out of the box so you can style components immediately.

## Scaffold defaults

`pyxle init` writes:

- `pages/styles/tailwind.css` – Tailwind entry file with `@tailwind` directives.
- `public/styles/tailwind.css` – Generated output (initially empty).
- `tailwind.config.cjs` – Targets files under `pages/**/*.{pyx,jsx,tsx}`.
- `package.json` scripts:

```json
{
  "scripts": {
    "dev:css": "tailwindcss -i ./pages/styles/tailwind.css -o ./public/styles/tailwind.css --watch",
    "build:css": "tailwindcss -i ./pages/styles/tailwind.css -o ./public/styles/tailwind.css --minify"
  }
}
```

## Development loop

1. Run `npm run dev:css` in a separate terminal (Tailwind CLI watches `pages/`).
2. Start `pyxle dev` – the dev server serves `public/styles/tailwind.css` and injects `<link rel="stylesheet" href="/styles/tailwind.css" />` when your `HEAD` references it.
3. Edit `.pyx` files; Tailwind picks up class usage automatically.

## Production build

`pyxle build` does not run Tailwind for you—invoke `npm run build:css` before running the build or wire it into your CI pipeline. The build pipeline copies the final `public/` directory (including CSS) into `dist/public`.

## Compare with Next.js

- Similar to using the Tailwind CLI alongside `next dev`. There is no automatic PostCSS integration inside Pyxle, so you fully control the CSS build.
- Because loaders run on the server, you can read Tailwind tokens in Python if you expose them as JSON (custom workflow).

See [Global styles & scripts](global-styles-and-scripts.md) for configuring additional CSS/JS files that should load on every page.
