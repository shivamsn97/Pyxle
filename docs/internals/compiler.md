# Compiler Internals

The compiler turns `.pyx` files into three artifacts: a server module, a client module, and a metadata JSON record. Entry point: `pyxle/compiler/core.py`.

## Pipeline

1. **Parse** – `PyxParser` (in `parser.py`) splits the file into Python + JSX segments, validates loader rules, extracts HEAD entries, and records line numbers for error reporting.
2. **Route mapping** – `_relative_page_path()` finds the path below `pages/` and `route_path_variants_from_relative()` converts it into `/foo` + aliases.
3. **Write artifacts** – `writers.ArtifactWriter` emits:
   - Server module (`.pyxle-build/server/pages/foo.py`) that imports your loader and wraps it with SSR helpers.
   - Client module (`.pyxle-build/client/pages/foo.jsx`) that contains the JSX portion and exports metadata used by the router.
   - Metadata JSON (`.pyxle-build/metadata/pages/foo.json`) describing the loader, head, slots, and layout lineage.

## Error handling

- All compile errors raise `CompilationError` with a mapped line number so editors can highlight the offending line.
- Examples: missing `@server`, loader inside a class, invalid HEAD assignment, inconsistent indentation.

## JSX imports

`pyxle/compiler/jsx_imports.py` hoists required imports (React, `pyxle/client`) and injects helper code (e.g., `createSlots`). The compiler leaves your custom imports untouched.

## Incremental builds

`pyxle/devserver/build.py` calls `compile_file()` only when a file hash changes. Deleted files trigger `_remove_page_artifacts()` so stale outputs disappear.

## Compare with Next.js

Think of this as the `.next/server/app/...` output. Unlike Next.js, Pyxle compiles Python and JSX at the same time, so there is no separate bundler stage for the server component.

Related docs:
- [SSR renderer](ssr.md)
- [Loader lifecycle](../fundamentals/loader-lifecycle.md)
