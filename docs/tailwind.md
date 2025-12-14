# Tailwind CSS Integration Guide

Pyxle uses Vite under the hood, so adding Tailwind follows the same workflow as
any React + Vite project. The steps below assume you already ran `pyxle init`
and are inside the generated project directory.

## 1. Install the npm dependencies

```bash
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

The `-p` flag writes both `tailwind.config.js` and `postcss.config.cjs` so Vite
knows how to process `@tailwind` directives.

## 2. Point Tailwind at `.pyx` files

Edit `tailwind.config.js` to include Pyxle's page formats:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './pages/**/*.{pyx,jsx,js,ts,tsx}',
    './.pyxle-build/client/pages/**/*.jsx',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
```

The second glob ensures compiled JSX emitted by the Pyxle compiler is also
scanned when Tailwind runs in production.

## 3. Create a source stylesheet

Create `pages/styles/tailwind.css` (or any path you prefer) and add the base
Tailwind directives:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

Commit this file to version control so the dev server can detect changes.

## 4. Import the stylesheet from your page code

Any `.pyx` file can import CSS inside the JavaScript section. The scaffolded
homepage already includes a reminder comment—uncomment the import once the file
exists:

```jsx
// import './styles/tailwind.css';
```

Because Pyxle bundles JSX through Vite, the CSS import behaves the same as a
regular React project.

## 5. Optional: add npm scripts

Update `package.json` with a helper script so you can build Tailwind output
separately when needed:

```json
{
  "scripts": {
    "tailwind:watch": "tailwindcss -i ./pages/styles/tailwind.css -o ./pages/styles/tailwind.out.css --watch"
  }
}
```

This is optional—the dev server already bundles your CSS when you import it. The
script is useful when you want to pre-build styles for CI or production images.

## 6. Run the dev server

```bash
pyxle dev
```

Tailwind classes are now available everywhere you write JSX. Restart the dev
server whenever you modify `tailwind.config.js` so Vite picks up the new glob
patterns.
