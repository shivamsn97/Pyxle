from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from typer.testing import CliRunner

from pyxle_langkit.cli import app


runner = CliRunner()


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_lint_exits_non_zero_on_compiler_error(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "pages" / "bad.pyx",
        dedent(
            """
            @server
            def bad_loader(request):
                return {}

            export default function Page() {
                return <div />;
            }
            """
        ).strip("\n"),
    )

    result = runner.invoke(app, ["lint", str(source)])

    assert result.exit_code == 1
    assert "pyxle/compiler" in result.output


def test_lint_exits_non_zero_when_error_issues_exist(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "pages" / "bad.pyx",
        dedent(
            """
            @server
            async def loader(request):
                return missing_value
            """
        ).strip("\n"),
    )

    result = runner.invoke(app, ["lint", str(source)])

    assert result.exit_code == 1
    assert "pyflakes/UndefinedName" in result.output
