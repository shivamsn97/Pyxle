"""Typer CLI exposing the language tooling for local experimentation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from pyxle.compiler.exceptions import CompilationError

from .lint import PyxLinter
from .parser import PyxLanguageParser
from .service import PyxLanguageService

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def parse(source: Annotated[Path, typer.Argument(help="Path to a .pyx file")]) -> None:
    """Print the parsed document (Python + JSX segmentation info)."""

    parser = PyxLanguageParser()
    try:
        document = parser.parse_path(source)
    except CompilationError as exc:
        location = f"line {exc.line_number}" if exc.line_number is not None else "unknown line"
        typer.secho(f"[error] parse failed at {location}: {exc.message}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
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
    try:
        issues = linter.lint_path(source)
    except CompilationError as exc:
        location = f"{exc.line_number}:1" if exc.line_number is not None else "?"
        typer.secho(
            f"[error] pyxle/compiler @ {location} — {exc.message}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.secho(f"[error] react/analyzer @ ? — {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    if not issues:
        typer.secho("✔ No issues found", fg=typer.colors.GREEN)
        return

    has_errors = False
    for issue in issues:
        if issue.severity == "error":
            has_errors = True
        location = "?"
        if issue.line is not None:
            col = issue.column if issue.column is not None else "?"
            location = f"{issue.line}:{col}"
        typer.echo(f"[{issue.severity}] {issue.rule} @ {location} — {issue.message}")
    if has_errors:
        raise typer.Exit(code=1)


@app.command()
def outline(source: Annotated[Path, typer.Argument(help="Path to a .pyx file")]) -> None:
    """Print a compact symbol outline for editors."""

    service = PyxLanguageService()
    try:
        symbols = service.outline(source)
    except CompilationError as exc:
        location = f"line {exc.line_number}" if exc.line_number is not None else "unknown line"
        typer.secho(f"[error] outline failed at {location}: {exc.message}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.secho(f"[error] outline failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    if not symbols:
        typer.echo("(no symbols detected)")
        return

    for symbol in symbols:
        location = symbol.line if symbol.line is not None else "?"
        detail = f" — {symbol.detail}" if symbol.detail else ""
        typer.echo(f"{symbol.kind:>15}  {symbol.name}  (line {location}){detail}")


if __name__ == "__main__":  # pragma: no cover
    app()
