# Pyxle LangKit

Language tooling (parser, linting, and IDE helpers) for `.pyx` files. LangKit reuses Pyxle's production compiler for Python/React separation, CPython's `ast` module for server-side validation, and Babel's JSX parser for client-side analysis so no custom language grammars are required. Install the optional extras via `pip install "pyxle[langkit]"` to pull in the `pygls` dependency used by the language server.

## Features

1. **Document Parser** – Wraps `pyxle.compiler.parser.PyxParser` to expose a stable `PyxDocument` structure with line mapping helpers for IDE integrations.
2. **Linting CLI** – Validates Python blocks via CPython `ast.parse` and JSX blocks via Babel (`@babel/parser`). Reports syntax errors, loader placement issues, and hydration risks detected during parsing.
3. **Language Service Helpers** – Builds document outlines, exposes loader metadata, and surfaces JSX export symbols for editor extensions or language servers.
4. **React Analysis Bridge** – Calls a small Node.js runner (`js/react_parser_runner.mjs`) that relies on the official React/Babel parser so updates to JSX syntax never require custom grammars.

## Usage

```bash
# Install Babel dependency once inside this folder
(cd pyxle_langkit && npm install)

# Parse or lint `.pyx` files via CLI
python -m pyxle_langkit.cli parse pages/index.pyx
python -m pyxle_langkit.cli lint pages/index.pyx
python -m pyxle_langkit.cli outline pages/index.pyx

# Start the language server (stdio mode by default)
pyxle-langserver --stdio
pyxle-langserver --tcp 127.0.0.1 7000
```

The CLI prints structured JSON (parse) or tabular diagnostics (lint/outline). Editor plugins can import `pyxle_langkit.parser` and `pyxle_langkit.service` directly.

### VS Code extension scaffold

The repository now includes `editors/vscode-pyxle/`, a minimal VS Code extension that:

1. Registers `.pyx` as a custom language with a TextMate grammar embedding Python + JSX scopes.
2. Launches the shared `pyxle-langserver` binary via stdio (configurable command/args).
3. Publishes diagnostics + outline data supplied by LangKit.

Install dependencies and start the extension in VS Code:

```bash
cd editors/vscode-pyxle
npm install
npm run compile   # optional if you add build tooling; plain JS works out of the box
code .            # press F5 to launch the extension development host
```

Other editors can point their LSP clients at `pyxle-langserver --stdio` or `--tcp` to reuse the same tooling without bespoke integrations.

## Node Dependency

LangKit never reimplements the React grammar. Instead it shells out to Node.js and `@babel/parser`. The first `npm install` inside `pyxle_langkit/` installs this dependency. The Python helpers surface a clear error message if the Node runner fails or has not been installed yet.
