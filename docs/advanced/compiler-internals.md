# Compiler Internals

The Pyxle compiler transforms `.pyx` files into separate Python and JSX artifacts. This document explains how the compilation process works.

## Compilation overview

When you run `pyxle dev` or `pyxle build`, the compiler:

1. Scans the `pages/` directory for `.pyx` files
2. Parses each file to separate Python from JSX
3. Writes server-side Python modules to `.pyxle-build/server/`
4. Writes client-side JSX modules to `.pyxle-build/client/`
5. Generates layout composition wrappers in `.pyxle-build/routes/`
6. Creates a Vite configuration at `.pyxle-build/vite.config.js`

## The parser

The parser (`pyxle/compiler/parser.py`) is a state-machine that classifies each line as Python or JSX.

### Line classification

Lines are classified as Python if they match common Python patterns:

- `import ...` or `from ... import ...`
- `def ...` or `async def ...`
- `class ...`
- Decorator lines starting with `@`
- Control flow: `if`, `for`, `while`, `try`, `except`, `finally`, `with`
- Continuation of multi-line Python constructs (strings, brackets)

Everything else is treated as JSX.

### What the parser extracts

| Artifact | Description |
|----------|-------------|
| `python_code` | All Python lines concatenated |
| `jsx_code` | All JSX lines concatenated |
| `loader` | `@server` function metadata (name, line number, parameters) |
| `actions` | `@action` function metadata (name, line number, parameters) |
| `head_elements` | Static `HEAD` variable content |
| `head_is_dynamic` | Whether `HEAD` is a callable |
| `head_jsx_blocks` | `<Head>...</Head>` JSX blocks extracted for server-side use |
| `script_declarations` | `<Script>` component props |
| `image_declarations` | `<Image>` component props |

### Validation

The parser enforces:

- At most one `@server` loader per file
- `@server` functions must be `async`
- `@action` functions must be `async`
- Loader and action names must be valid Python identifiers
- No circular decorator stacking

## Code generation

### Server module (`.pyxle-build/server/pages/*.py`)

The compiled Python module contains:

```python
from pyxle.runtime import server, action

# Original imports from the .pyx file
from datetime import datetime

# Loader function
@server
async def load_page(request):
    return {"now": datetime.now().isoformat()}

# Action functions
@action
async def delete_item(request):
    body = await request.json()
    return {"deleted": True}
```

### Client module (`.pyxle-build/client/pages/*.jsx`)

The compiled JSX module contains:

```jsx
import React from 'react';
import { Head } from 'pyxle/client';

export default function MyPage({ data }) {
  return (
    <>
      <Head>
        <title>My Page</title>
      </Head>
      <h1>{data.now}</h1>
    </>
  );
}
```

### Composed route module (`.pyxle-build/routes/*.jsx`)

When layouts exist, the compiler generates a wrapper:

```jsx
import Page from '../client/pages/index.jsx';
import Layout from '../client/pages/layout.jsx';

const WRAPPERS = [
  { kind: 'layout', component: Layout, reset: false },
];

export default function PyxleWrappedPage(props) {
  // Nests: Layout(Page)
  let element = <Page {...props} />;
  for (const wrapper of WRAPPERS.reverse()) {
    const Wrapper = wrapper.component;
    element = <Wrapper>{element}</Wrapper>;
  }
  return element;
}
```

## Vite configuration

The compiler generates `.pyxle-build/vite.config.js` that:

- Configures `@vitejs/plugin-react` for JSX transforms and React Refresh
- Sets the `root` to the build directory
- Maps import aliases for `pyxle/client`
- Injects `PYXLE_PUBLIC_*` environment variables via Vite's `define` option

## Incremental compilation

During `pyxle dev`, the file watcher triggers recompilation only for changed files:

1. The watcher detects a file change in `pages/`
2. Only the changed `.pyx` file is recompiled
3. The server module is re-imported (with module cache invalidation)
4. Vite's HMR picks up the client-side changes automatically

## Build artifacts

After `pyxle build`, the output structure is:

```
dist/
  server/              # Compiled Python modules
  client/              # Vite-bundled JS/CSS assets
  page-manifest.json   # Route-to-asset mapping
```

The `page-manifest.json` maps each route to its client-side assets:

```json
{
  "/": {
    "client": {
      "file": "assets/index-abc123.js",
      "css": ["assets/index-def456.css"]
    }
  }
}
```
