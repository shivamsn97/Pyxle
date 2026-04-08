# Project Structure

After running `pyxle init my-app`, you get this file tree:

```
my-app/
  pages/
    api/
      pulse.py            # Example API route
    styles/
      tailwind.css        # Tailwind CSS input file
    index.pyx             # Home page (Python + React)
    layout.pyx            # Root layout wrapper (React only)
  public/
    branding/             # SVG logos and assets
    styles/
      tailwind.css        # Compiled Tailwind output (generated)
    favicon.ico
  package.json            # Node.js dependencies and scripts
  pyxle.config.json       # Framework configuration
  requirements.txt        # Python dependencies
  tailwind.config.cjs     # Tailwind CSS configuration
  postcss.config.cjs      # PostCSS configuration
  .gitignore
```

## Key directories

### `pages/`

The pages directory is the heart of your app. Every `.pyx` file here becomes a route, and every `.py` file under `pages/api/` becomes an API endpoint.

```
pages/
  index.pyx        -->  /
  about.pyx        -->  /about
  blog/
    index.pyx      -->  /blog
    [slug].pyx     -->  /blog/:slug
  api/
    pulse.py       -->  /api/pulse
    users.py       -->  /api/users
```

See [Routing](../core-concepts/routing.md) for the full rules.

### `public/`

Static files served directly. Anything in `public/` is available at the root URL:

- `public/favicon.ico` --> `http://localhost:8000/favicon.ico`
- `public/branding/logo.svg` --> `http://localhost:8000/branding/logo.svg`

### `.pyxle-build/` (generated at runtime)

Created automatically when you run `pyxle dev` or `pyxle build`. Contains compiled Python modules, transpiled JSX, and Vite configuration. This directory is gitignored -- do not edit files here.

```
.pyxle-build/
  server/           # Compiled Python modules from @server blocks
  client/           # Transpiled JSX components for Vite
  routes/           # Composed page+layout wrappers
  vite.config.js    # Auto-generated Vite configuration
```

## Key files

### `pages/index.pyx`

A `.pyx` file combines Python server logic with a React component. The scaffold's index page demonstrates:

- `@server` decorator for data loading
- React JSX for the UI
- The `<Head>` component from `pyxle/client` for document `<head>` elements

```python
# Python section
from pyxle import __version__

@server
async def load_home(request):
    return {"message": "Hello, world!"}
```

```jsx
// JSX section -- receives loader data as props
import { Head } from 'pyxle/client';

export default function HomePage({ data }) {
  return (
    <>
      <Head>
        <title>My App</title>
      </Head>
      <h1>{data.message}</h1>
    </>
  );
}
```

### `pages/layout.pyx`

The root layout wraps every page. It is JSX-only (no Python section needed):

```jsx
export default function AppLayout({ children }) {
  return (
    <div className="min-h-screen">
      {children}
    </div>
  );
}
```

### `pages/api/pulse.py`

A plain Python file that serves as an API endpoint. Returns JSON by default:

```python
from starlette.requests import Request
from starlette.responses import JSONResponse

async def get(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})
```

### `pyxle.config.json`

Framework configuration. The scaffold ships with a minimal config:

```json
{
  "middleware": []
}
```

See [Configuration Reference](../reference/configuration.md) for all available options.

### `package.json`

Defines Node.js dependencies and npm scripts:

| Script | Purpose |
|--------|---------|
| `npm run dev` | Start Vite dev server (used internally by `pyxle dev`) |
| `npm run build` | Build CSS + bundle with Vite (used by `pyxle build`) |
| `npm run dev:css` | Watch Tailwind CSS compilation |
| `npm run build:css` | One-shot minified Tailwind build |

### `tailwind.config.cjs`

Tailwind CSS configuration. The scaffold configures it to scan your `pages/` directory for class names:

```javascript
module.exports = {
  content: ['./pages/**/*.{pyx,jsx,js,tsx,ts}'],
  darkMode: 'class',
  // ...
};
```

## Next steps

- Learn how `.pyx` files work: [`.pyx` Files](../core-concepts/pyx-files.md)
- Understand routing: [Routing](../core-concepts/routing.md)
