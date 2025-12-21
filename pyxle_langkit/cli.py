"""Typer CLI exposing the language tooling for local experimentation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .lint import PyxLinter
from .parser import PyxLanguageParser
from .service import PyxLanguageService

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def parse(source: Annotated[Path, typer.Argument(help="Path to a .pyx file")]) -> None:
    """Print the parsed document (Python + JSX segmentation info)."""

    parser = PyxLanguageParser()
    document = parser.parse_path(source)
    payload = {
        "path": str(document.path),
        "has_python": document.has_python,
        "has_jsx": document.has_jsx,
        "loader": (
            {
                "name": document.loader.name,
                "line": document.loader.line_number,
                "parameters": list(document.loader.parameters),
            }
            if document.loader
            else None
        ),
        "head": {
            "elements": list(document.head_elements),
            "dynamic": document.head_is_dynamic,
        },
        "python_lines": len(document.python_line_numbers),
    }
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def lint(source: Annotated[Path, typer.Argument(help="Path to a .pyx file")]) -> None:
    """Run lint checks for the given `.pyx` file."""

    linter = PyxLinter()
    issues = linter.lint_path(source)
    if not issues:
        typer.secho("✔ No issues found", fg=typer.colors.GREEN)
        return

    for issue in issues:
        location = "?"
        if issue.line is not None:
            col = issue.column if issue.column is not None else "?"
            location = f"{issue.line}:{col}"
        typer.echo(f"[{issue.severity}] {issue.rule} @ {location} — {issue.message}")


@app.command()
def outline(source: Annotated[Path, typer.Argument(help="Path to a .pyx file")]) -> None:
    """Print a compact symbol outline for editors."""

    service = PyxLanguageService()
    symbols = service.outline(source)
    if not symbols:
        typer.echo("(no symbols detected)")
        return

    for symbol in symbols:
        location = symbol.line if symbol.line is not None else "?"
        detail = f" — {symbol.detail}" if symbol.detail else ""
        typer.echo(f"{symbol.kind:>15}  {symbol.name}  (line {location}){detail}")


if __name__ == "__main__":  # pragma: no cover
    app()
