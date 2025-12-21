# LangKit, LSP, and Editor Tooling

The `pyxle_langkit/` package provides language smarts for editors so `.pyx` feels first-class.

## CLI

`pyxle-langkit` exposes commands via `pyxle_langkit/cli.py`:

- `pyxle-langkit lint <file>` – parses the `.pyx` file and reports compiler errors without running the whole build.
- `pyxle-langkit parse <file>` – dumps the Python/JSX segments for debugging.

## Language Server (LSP)

- Implemented in `pyxle_langkit/lsp.py`.
- Speaks the Language Server Protocol so VS Code (and other editors) can highlight errors, provide go-to-definition for loaders, and eventually surface slot metadata.
- Reuses the same parser (`pyxle_langkit/parser.py`) to stay in sync with the main compiler.

## VS Code extension

Found in `editors/vscode-pyxle/`:

- Syntax highlighting for `.pyx` files via `syntaxes/pyx.tmLanguage.json`.
- Language configuration for comment toggling, bracket matching, etc.
- Commands to run the linter or open docs quickly.

Install locally by running `npm install && npm run package` inside the extension folder, then load the VSIX in VS Code.

## Compare with Next.js

Just like Next.js relies on TypeScript/ESLint integrations, Pyxle projects benefit from LangKit to catch loader mistakes (missing `@server`, wrong `request` parameter name, etc.) before the dev server runs.

Roadmap items in `tasks/phase_*` describe upcoming tooling work—check them before hacking new features so documentation stays aligned.

### Daily workflow

- Add `"pyxle-langkit": "latest"` under `devDependencies` to keep CLI checks consistent in CI.
- Use `pyxle-langkit lint pages/**/*.pyx` in pre-commit hooks to block malformed files.
- Pair the VS Code extension with Python/TS formatters (Black, Prettier) for best results.

---
**Navigation:** [← Previous](index.md) | [Next →](testing.md)
