# Pyxle Language Tools (VS Code)

VS Code extension that wires `.pyx` files to the shared LangKit language server.

## Setup

```bash
cd editors/vscode-pyxle
npm install
```

Launch the extension development host:

1. Open the folder in VS Code (`code editors/vscode-pyxle`).
2. Press `F5` to start a new Extension Development Host window.
3. Open a `.pyx` file — syntax highlighting and diagnostics should appear immediately.

The extension uses the global `pyxle-langserver` executable. Override the command or arguments via `Settings → Pyxle Language Server` or in `settings.json`:

```json
{
  "pyxleLangserver.command": "/path/to/pyxle-langserver",
  "pyxleLangserver.args": ["--stdio"]
}
```

Because the server implements the Language Server Protocol, any other LSP-compatible editor (Neovim, Sublime, JetBrains, etc.) can reuse it without bespoke integrations.
